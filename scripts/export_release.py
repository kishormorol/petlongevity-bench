#!/usr/bin/env python3
"""Build a redistributable release bundle from the working corpus.

    python scripts/export_release.py --output release/

`data/corpus/` holds verbatim PubMed abstracts, and we do not hold the right to
redistribute all of them. The registry records a per-paper `license` string and
`open_access_status` captured at retrieval, which is what makes a precise split
possible instead of dropping the corpus wholesale:

  * open access, with a licence that permits redistribution -> text ships
  * unknown or absent licence -> text is withheld; the release carries the
    PMID, the DOI, the retrieval metadata and the SHA-256 of the text we
    scored, so a user fetches the abstract themselves and can prove they got
    the same bytes.

Offsets are always kept. An annotation anchored by `source_start_offset` /
`source_end_offset` against a hash-verified abstract is fully reproducible
without us shipping the text, which is the standard shape for a PubMed-derived
benchmark.

The bundle is inert data plus a manifest. It does not touch `data/`.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

# A licence string counts as redistributable only if it names a Creative
# Commons grant. "unknown", empty, and publisher permission notices
# ("Reprints and permissions information is available at...") do not.
REDISTRIBUTABLE = ("creativecommons.org", "creative commons", "cc by", "cc-by")


def licence_family(license_text: str | None, oa_status: str | None) -> str:
    """Coarse licence family, because the variants are not interchangeable.

    CC BY redistributes freely. NC forbids commercial use and ND forbids
    derivatives — a benchmark that ships both under one permissive dataset
    licence would be making a promise it cannot keep, so they are counted
    separately and the caller decides.
    """
    lic = (license_text or "").strip().strip('"').lower()
    oa = (oa_status or "").strip().strip('"').lower()
    if not lic or lic == "null":
        return "none"
    if not any(marker in lic for marker in REDISTRIBUTABLE):
        return "other"  # e.g. a publisher reprints-and-permissions notice
    if oa != "oa":
        return "cc-but-not-oa"
    nc = "-nc" in lic or "noncommercial" in lic or "non-commercial" in lic
    nd = "-nd" in lic or "noderiv" in lic or "no derivatives" in lic
    if nc and nd:
        return "cc-by-nc-nd"
    if nc:
        return "cc-by-nc"
    if nd:
        return "cc-by-nd"
    return "cc-by"


def is_redistributable(license_text: str | None, oa_status: str | None, *, allow_nc_nd: bool) -> bool:
    fam = licence_family(license_text, oa_status)
    if fam == "cc-by":
        return True
    return allow_nc_nd and fam in {"cc-by-nc", "cc-by-nd", "cc-by-nc-nd"}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def annotation_pmid(ann: dict) -> str:
    """v0.1 annotations carry `pmid`; draft pairs carry `paper_id` as `PMID:<n>`."""
    pmid = str(ann.get("pmid") or "").strip()
    if pmid:
        return pmid
    for key in ("paper_id", "source_id"):
        value = str(ann.get(key) or "")
        if value.startswith("PMID:"):
            return value[len("PMID:"):]
    return ""


def withhold_text(ann: dict) -> None:
    """Null every field that can hold a verbatim excerpt, keeping offsets."""
    for key in ("evidence_quote", "claim_text"):
        if key in ann:
            ann[key] = None
    span = ann.get("supporting_span")
    if isinstance(span, dict):
        span["text"] = None
    ann["evidence_quote_withheld"] = True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default="data/corpus/registry.csv")
    ap.add_argument("--annotations", default="data/gold/v0_1/annotations.jsonl")
    ap.add_argument("--output", default="release")
    ap.add_argument(
        "--allow-nc-nd",
        action="store_true",
        help="also ship text under NonCommercial/NoDerivatives licences. Off by "
             "default: those terms bind everyone who downloads the benchmark.",
    )
    args = ap.parse_args()

    registry_path = Path(args.registry)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    with registry_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print(f"{registry_path}: no rows", file=sys.stderr)
        return 1

    counts = Counter()
    families = Counter()
    open_pmids: set[str] = set()
    released = []
    for row in rows:
        pmid = (row.get("pmid") or "").strip().strip('"')
        abstract = row.get("abstract") or ""
        fam = licence_family(row.get("license"), row.get("open_access_status"))
        families[fam] += 1
        ok = is_redistributable(row.get("license"), row.get("open_access_status"), allow_nc_nd=args.allow_nc_nd)
        counts["redistributable" if ok else "text_withheld"] += 1
        if ok:
            open_pmids.add(pmid)

        record = {k: v for k, v in row.items() if k != "abstract"}
        # Always publishable: it identifies the text without reproducing it.
        record["abstract_sha256"] = sha256(abstract) if abstract else None
        record["abstract_chars"] = len(abstract) if abstract else 0
        record["text_included"] = ok
        record["licence_family"] = fam
        record["abstract"] = abstract if ok else None
        released.append(record)

    with (out / "registry.jsonl").open("w", encoding="utf-8") as fh:
        for record in released:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Annotations: offsets and labels always ship. Quotes, claim sentences and
    # span text are verbatim excerpts in both the v0.1 and the draft-pair
    # schemas, so they follow their source paper's licence.
    ann_path = Path(args.annotations)
    ann_counts = Counter()
    if ann_path.exists():
        with (out / "annotations.jsonl").open("w", encoding="utf-8") as fh:
            for line in ann_path.open(encoding="utf-8"):
                ann = json.loads(line)
                keep_quote = annotation_pmid(ann) in open_pmids
                ann_counts["quote_included" if keep_quote else "quote_withheld"] += 1
                ann.pop("source_text_path", None)  # a path inside this repo, meaningless in a bundle
                if not keep_quote:
                    withhold_text(ann)
                fh.write(json.dumps(ann, ensure_ascii=False) + "\n")

    manifest = {
        "bundle": "petlongevity-bench-release",
        "source_registry": str(registry_path),
        "papers": len(released),
        "papers_with_text": counts["redistributable"],
        "papers_text_withheld": counts["text_withheld"],
        "licence_families": dict(sorted(families.items())),
        "nc_nd_included": args.allow_nc_nd,
        "annotations": sum(ann_counts.values()),
        "annotation_quotes_included": ann_counts["quote_included"],
        "annotation_quotes_withheld": ann_counts["quote_withheld"],
        "policy": (
            "Abstract text and verbatim evidence quotes ship only for papers whose "
            "recorded licence is an open Creative Commons grant. Every other record "
            "carries PMID, DOI, retrieval metadata and abstract_sha256 so the text can "
            "be re-fetched and verified byte-for-byte."
        ),
        "refetch": "petbench snapshot-pubmed --query '<registry search_query>' --cutoff <cutoff> --output <path>",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
