"""Rights-aware intake and review queue for paper-level evidence annotation."""
from __future__ import annotations

import csv
import re
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .io import load_jsonl, sha256_file, write_jsonl


LAWFUL_ACCESS_BASES = {"pmc_open_access", "institutional_access", "author_provided", "publisher_permission"}


def _portable_relative(path: Path, root: Path) -> str:
    """Return a platform-independent relative path for JSON/CSV contracts."""
    return path.relative_to(root).as_posix()


def _same_portable_path(left: str, right: str) -> bool:
    return Path(left).as_posix() == Path(right).as_posix()


def _xml_name(element: ET.Element) -> str:
    """Return an XML tag name without its optional namespace."""
    return element.tag.rsplit("}", 1)[-1]


def _xml_text(element: ET.Element) -> str:
    """Collapse XML inline markup without changing the words shown to reviewers."""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def _pmc_body_text(root: ET.Element) -> str:
    """Extract a readable article body from PMC JATS XML.

    Front matter (journal metadata, affiliations, identifiers) and back matter (references)
    are intentionally excluded. The resulting text remains the checksum-bound annotation source,
    so portal selection offsets always refer to exactly what the reviewer read.
    """
    body = next((element for element in root.iter() if _xml_name(element) == "body"), None)
    if body is None:
        raise ValueError("PMC article XML has no article body")
    parents = {child: parent for parent in body.iter() for child in parent}

    def is_in_table(element: ET.Element) -> bool:
        current = parents.get(element)
        while current is not None:
            if _xml_name(current) == "table-wrap":
                return True
            current = parents.get(current)
        return False

    blocks: list[str] = []
    for element in body.iter():
        tag = _xml_name(element)
        if tag == "table-wrap":
            label = next((_xml_text(child) for child in element if _xml_name(child) == "label"), "")
            caption = next((_xml_text(child) for child in element if _xml_name(child) == "caption"), "")
            rows = []
            for row in element.iter():
                if _xml_name(row) != "tr":
                    continue
                cells = [_xml_text(cell) for cell in row if _xml_name(cell) in {"td", "th"}]
                if cells:
                    rows.append(" | ".join(cells).rstrip(" |"))
            heading = " ".join(part for part in (label, caption) if part)
            blocks.append("\n".join(part for part in ([heading] if heading else []) + rows))
        elif tag in {"title", "p", "list-item"} and not is_in_table(element):
            text = _xml_text(element)
            if text:
                blocks.append(text)
    return "\n\n".join(blocks)


def fulltext_inventory(registry_path: str | Path) -> list[dict[str, Any]]:
    """List every registered paper and the next lawful full-text review action."""
    rows = load_jsonl(registry_path)
    inventory = []
    for paper in rows:
        pmcid = paper.get("pmcid")
        if paper.get("full_text_available") and paper.get("local_source_path"):
            status, action = "local_rights_cleared", "Prepare exact Methods/Results evidence spans from the local source."
        elif pmcid and paper.get("license"):
            status, action = "pmc_access_to_confirm", "Open the PMC record, confirm current access and license, then save only a lawfully obtained source."
        else:
            status, action = "lawful_source_required", "Obtain a lawful full-text copy before making paper-level annotations."
        inventory.append({
            "paper_id": paper["paper_id"], "pmid": paper.get("pmid"), "pmcid": pmcid,
            "title": paper["title"], "publication_date": paper["publication_date"], "species": paper["species"],
            "pubmed_url": paper["pubmed_url"],
            "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else None,
            "recorded_license": paper.get("license"), "fulltext_status": status, "next_action": action,
        })
    return sorted(inventory, key=lambda item: (item["publication_date"], item["paper_id"]))


def write_fulltext_queue(registry_path: str | Path, output_dir: str | Path) -> dict[str, int]:
    """Write a clinician-facing paper queue without generating scientific labels."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    inventory = fulltext_inventory(registry_path)
    write_jsonl(output / "paper_inventory.jsonl", inventory)
    with (output / "paper_inventory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(inventory[0]) if inventory else ["paper_id"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory)
    (output / "README.md").write_text("""# Full-paper evidence review queue

This queue is the starting point for paper-level annotation. It is not a gold dataset and it
does not contain machine-generated scientific labels.

For each paper, first obtain a lawful full-text source. Record that source in
`fulltext_receipts.jsonl` using the required fields below, then run
`petbench validate-fulltext-receipts --receipts fulltext_receipts.jsonl --registry <registry> --base-dir <source-root>`.

Only after a receipt validates should reviewers create claim/evidence pairs. Each pair must cite
an exact span from the reviewed full text, retain the source checksum, and receive two independent
reviews plus adjudication before it can become gold.

For extracted local PMC sources, create the clinician's draft worksheet with
`petbench prepare-fulltext-worksheet --registry <registry> --receipts fulltext_receipts.jsonl --base-dir <review-dir> --output-dir <review-dir>`.
The resulting worksheet and annotation instructions contain no automatic scientific labels.

## Full-text receipt format

One JSON object per paper:

```json
{"paper_id":"PMID:123","lawful_access_basis":"pmc_open_access","license_or_permission":"CC BY 4.0","source_text_path":"sources/PMID_123.txt","source_text_sha256":"<sha256>","review_ready":true,"notes":"Text extracted from the lawfully accessed article."}
```

Allowed `lawful_access_basis` values are `pmc_open_access`, `institutional_access`,
`author_provided`, and `publisher_permission`. Do not put paywalled PDFs or text in the
repository unless the applicable license or permission allows it.
""", encoding="utf-8")
    return {"paper_count": len(inventory), "local_rights_cleared": sum(row["fulltext_status"] == "local_rights_cleared" for row in inventory), "needs_access_confirmation": sum(row["fulltext_status"] == "pmc_access_to_confirm" for row in inventory), "lawful_source_required": sum(row["fulltext_status"] == "lawful_source_required" for row in inventory)}


def extract_pmc_fulltext(registry_path: str | Path, corpus_dir: str | Path, output_dir: str | Path) -> dict[str, int]:
    """Extract reviewable text from locally verified PMC OA packages and write receipts."""
    corpus = Path(corpus_dir)
    output = Path(output_dir)
    source_dir = output / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    receipts: list[dict[str, Any]] = []
    skipped = 0
    for paper in load_jsonl(registry_path):
        package_name = paper.get("local_source_path")
        if not paper.get("full_text_available") or not package_name:
            skipped += 1
            continue
        package = corpus / package_name
        try:
            if package.name.endswith(".tar.gz"):
                with tarfile.open(package, "r:gz") as archive:
                    nxml = next(member for member in archive.getmembers() if member.name.endswith(".nxml"))
                    handle = archive.extractfile(nxml)
                    if handle is None:
                        raise OSError("PMC article XML cannot be extracted")
                    root = ET.fromstring(handle.read())
            else:
                root = ET.fromstring(package.read_bytes())
        except (OSError, StopIteration, tarfile.TarError, ET.ParseError) as exc:
            raise ValueError(f"cannot extract PMC source for {paper['paper_id']}: {exc}") from exc
        text = _pmc_body_text(root)
        destination = source_dir / f"{paper['paper_id'].replace(':', '_')}.txt"
        destination.write_text(text + "\n", encoding="utf-8", newline="\n")
        receipts.append({
            "paper_id": paper["paper_id"], "lawful_access_basis": "pmc_open_access",
            "license_or_permission": paper["license"],
            "source_text_path": _portable_relative(destination, output),
            "source_text_sha256": sha256_file(destination), "review_ready": True,
            "notes": f"Clean article body extracted from verified PMC source {package_name}; source SHA-256: {paper['source_sha256']}.",
        })
    write_jsonl(output / "fulltext_receipts.jsonl", receipts)
    return {"extracted": len(receipts), "skipped_without_local_fulltext": skipped}


def write_fulltext_annotation_worksheet(registry_path: str | Path, receipts_path: str | Path, base_dir: str | Path, output_dir: str | Path) -> dict[str, int]:
    """Create a clinician worksheet for draft full-paper claims, without labeling gold data."""
    errors = validate_fulltext_receipts(receipts_path, registry_path, base_dir)
    if errors:
        raise ValueError("cannot create worksheet from invalid full-text receipts")
    papers = {paper["paper_id"]: paper for paper in load_jsonl(registry_path)}
    receipts = load_jsonl(receipts_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    fields = ["paper_id", "paper_title", "species", "source_text_path", "source_text_sha256", "reviewer_id", "source_section", "start_char", "end_char", "exact_evidence_quote", "claim_text", "draft_label", "study_design", "outcome", "causal_interpretation", "reviewer_notes"]
    rows = [{"paper_id": receipt["paper_id"], "paper_title": papers[receipt["paper_id"]]["title"], "species": ";".join(papers[receipt["paper_id"]]["species"]), "source_text_path": receipt["source_text_path"], "source_text_sha256": receipt["source_text_sha256"], **{field: "" for field in fields[5:]}} for receipt in receipts]
    with (output / "fulltext_annotation_worksheet.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    (output / "annotation_instructions.md").write_text("""# Draft full-paper annotation worksheet

This worksheet is for a clinician to create **draft** claim/evidence records from the validated
full-paper sources. It is not a gold dataset and must not be scored or published as one.

For every candidate claim, add a row (copy the paper metadata from the starter row) and:

1. Read the full source in `sources/` before deciding anything.
2. State the paper section and copy an exact supporting or contradicting excerpt.
3. Record the character start and end offsets of that excerpt in the extracted text source.
4. Choose `supported`, `contradicted`, or `insufficient` only for the claim as written.
5. Record the actual study design, outcome, and causal interpretation. Do not infer causality,
   lifespan, cross-species applicability, or clinical utility beyond the paper.
6. Put uncertainties, subgroup limits, missing methods, and reason for an `insufficient` judgment
   in reviewer notes.

When the worksheet is complete, the coordinator will validate every span against the source,
convert eligible rows to the repository's claim/evidence contract, obtain an independent second
review, and adjudicate disagreements. No row becomes gold at this stage.
""", encoding="utf-8")
    return {"paper_rows": len(rows)}


def validate_fulltext_draft_submission(submission_path: str | Path, receipts_path: str | Path, base_dir: str | Path) -> list[dict[str, Any]]:
    """Validate a clinician portal JSONL download against its checksum-bound source text.

    A passing submission remains a draft: this function deliberately does not import records into
    gold data or decide scientific correctness.
    """
    base = Path(base_dir)
    if not Path(submission_path).is_file():
        raise ValueError("draft submission file is missing")
    receipts = {row["paper_id"]: row for row in load_jsonl(receipts_path)}
    required = {"paper_id", "paper_title", "species", "source_text_path", "source_text_sha256", "reviewer_id", "source_section", "start_char", "end_char", "exact_evidence_quote", "claim_text", "draft_label", "study_design", "outcome", "causal_interpretation", "reviewer_notes"}
    errors: list[dict[str, Any]] = []
    rows = load_jsonl(submission_path)
    if not rows:
        return [{"row": None, "paper_id": None, "path": "submission", "message": "at least one draft annotation is required"}]
    for index, row in enumerate(rows):
        paper_id = row.get("paper_id")
        if set(row) != required:
            errors.append({"row": index, "paper_id": paper_id, "path": "record", "message": "submission fields do not match the documented draft contract"})
            continue
        receipt = receipts.get(paper_id)
        if receipt is None:
            errors.append({"row": index, "paper_id": paper_id, "path": "paper_id", "message": "paper is not in the validated full-text receipt set"})
            continue
        for field in ("source_text_path", "source_text_sha256"):
            if field == "source_text_path" and _same_portable_path(row[field], receipt[field]):
                continue
            if row[field] != receipt[field]:
                errors.append({"row": index, "paper_id": paper_id, "path": field, "message": "does not match the validated source receipt"})
        for field in ("reviewer_id", "source_section", "claim_text", "study_design", "outcome", "causal_interpretation"):
            if not isinstance(row[field], str) or not row[field].strip():
                errors.append({"row": index, "paper_id": paper_id, "path": field, "message": "a non-empty value is required"})
        if row["draft_label"] not in {"supported", "contradicted", "insufficient"}:
            errors.append({"row": index, "paper_id": paper_id, "path": "draft_label", "message": "must be supported, contradicted, or insufficient"})
        start, end = row["start_char"], row["end_char"]
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            errors.append({"row": index, "paper_id": paper_id, "path": "offsets", "message": "start_char and end_char must be integers"})
            continue
        source = base / receipt["source_text_path"]
        text = source.read_text(encoding="utf-8")
        if start < 0 or end <= start or end > len(text):
            errors.append({"row": index, "paper_id": paper_id, "path": "offsets", "message": "offsets are outside the validated source text"})
        elif row["exact_evidence_quote"] != text[start:end]:
            errors.append({"row": index, "paper_id": paper_id, "path": "exact_evidence_quote", "message": "quote does not exactly match the source span"})
    return errors


def validate_fulltext_receipts(receipts_path: str | Path, registry_path: str | Path, base_dir: str | Path) -> list[dict[str, Any]]:
    """Validate lawful full-text receipts and checksum-bound source text for review."""
    receipts = load_jsonl(receipts_path)
    papers = {row["paper_id"]: row for row in load_jsonl(registry_path)}
    base = Path(base_dir)
    errors: list[dict[str, Any]] = []
    if not receipts:
        return [{"row": None, "paper_id": None, "path": "receipts", "message": "at least one full-text receipt is required"}]
    seen: set[str] = set()
    required = {"paper_id", "lawful_access_basis", "license_or_permission", "source_text_path", "source_text_sha256", "review_ready", "notes"}
    for row, receipt in enumerate(receipts):
        ident = receipt.get("paper_id")
        if set(receipt) != required:
            errors.append({"row": row, "paper_id": ident, "path": "receipt", "message": "receipt fields do not match the documented contract"})
        if ident in seen:
            errors.append({"row": row, "paper_id": ident, "path": "paper_id", "message": "duplicate paper receipt"})
        seen.add(ident)
        if ident not in papers:
            errors.append({"row": row, "paper_id": ident, "path": "paper_id", "message": "unknown paper_id"})
        if receipt.get("lawful_access_basis") not in LAWFUL_ACCESS_BASES:
            errors.append({"row": row, "paper_id": ident, "path": "lawful_access_basis", "message": "unrecognized lawful access basis"})
        if not isinstance(receipt.get("license_or_permission"), str) or not receipt["license_or_permission"].strip():
            errors.append({"row": row, "paper_id": ident, "path": "license_or_permission", "message": "license or permission is required"})
        if receipt.get("review_ready") is not True:
            errors.append({"row": row, "paper_id": ident, "path": "review_ready", "message": "receipt must explicitly be ready for review"})
        path = base / str(receipt.get("source_text_path", ""))
        try:
            path.resolve().relative_to(base.resolve())
        except ValueError:
            errors.append({"row": row, "paper_id": ident, "path": "source_text_path", "message": "source text must remain within base-dir"})
            continue
        if not path.is_file():
            errors.append({"row": row, "paper_id": ident, "path": "source_text_path", "message": "local source text is missing"})
        elif receipt.get("source_text_sha256") != sha256_file(path):
            errors.append({"row": row, "paper_id": ident, "path": "source_text_sha256", "message": "source text checksum does not match"})
    return errors
