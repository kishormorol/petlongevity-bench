"""Validation and agreement utilities for adjudicated M1/M2 datasets."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from .io import load_json, load_jsonl, sha256_file
from .schema import validate_records


DATASET_MANIFEST_SCHEMA = Path(__file__).parents[2] / "schemas" / "dataset_manifest_schema.json"
ANNOTATION_SCHEMA = Path(__file__).parents[2] / "schemas" / "annotation_adjudication_schema.json"
RESEARCH_MANIFEST_SCHEMA = Path(__file__).parents[2] / "schemas" / "research_dataset_manifest_schema.json"
PAPER_REGISTRY_SCHEMA = Path(__file__).parents[2] / "schemas" / "paper_registry_schema.json"
CLAIM_EVIDENCE_SCHEMA = Path(__file__).parents[2] / "schemas" / "claim_evidence_schema.json"
M2_LABELS = ("supported", "contradicted", "insufficient")


def validate_dataset(manifest_path: str | Path, records_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return schema and gold-review errors for an adjudicated M1/M2 dataset."""
    manifest_file = Path(manifest_path)
    manifest = load_json(manifest_file)
    errors = validate_records([manifest], DATASET_MANIFEST_SCHEMA)
    if records_path is None:
        records_path = manifest_file.parent / manifest.get("records_file", "")
    records_file = Path(records_path)
    try:
        records = load_jsonl(records_file)
    except (OSError, ValueError) as exc:
        errors.append({"row": None, "record_id": None, "path": "records_file", "message": str(exc)})
        return errors
    errors.extend(validate_records(records, ANNOTATION_SCHEMA))
    dataset_status = manifest.get("dataset_status")
    task = manifest.get("task")
    for row, record in enumerate(records):
        if task and record.get("task") != task:
            errors.append({"row": row, "record_id": record.get("annotation_id"), "path": "task", "message": "record task must match manifest task"})
        if dataset_status == "gold":
            review = record.get("review", {})
            if review.get("status") != "adjudicated":
                errors.append({"row": row, "record_id": record.get("annotation_id"), "path": "review.status", "message": "gold records must be adjudicated"})
            for role in ("annotator_a", "annotator_b", "adjudicator"):
                if not review.get(role, {}).get("annotator_id"):
                    errors.append({"row": row, "record_id": record.get("annotation_id"), "path": f"review.{role}", "message": "gold records require a reviewer identifier"})
    return errors


def validate_research_dataset(manifest_path: str | Path) -> list[dict[str, Any]]:
    """Validate a registry-linked real-paper claim/evidence corpus without adding labels."""
    manifest_file=Path(manifest_path); manifest=load_json(manifest_file)
    errors=validate_records([manifest],RESEARCH_MANIFEST_SCHEMA)
    try:
        papers=load_jsonl(manifest_file.parent / manifest.get("paper_registry_file",""))
        pairs=load_jsonl(manifest_file.parent / manifest.get("claim_evidence_file",""))
    except (OSError,ValueError) as exc:
        return errors+[{"row":None,"record_id":None,"path":"dataset_files","message":str(exc)}]
    errors.extend(validate_records(papers,PAPER_REGISTRY_SCHEMA))
    errors.extend(validate_records(pairs,CLAIM_EVIDENCE_SCHEMA))
    paper_ids=[paper.get("paper_id") for paper in papers]
    if len(set(paper_ids)) != len(paper_ids):
        errors.append({"row":None,"record_id":None,"path":"paper_registry","message":"duplicate paper_id"})
    indexed={paper.get("paper_id"):paper for paper in papers}
    pair_ids=[pair.get("pair_id") for pair in pairs]
    if len(set(pair_ids)) != len(pair_ids):
        errors.append({"row":None,"record_id":None,"path":"claim_evidence","message":"duplicate pair_id"})
    for row,pair in enumerate(pairs):
        paper=indexed.get(pair.get("paper_id")); record_id=pair.get("pair_id")
        if not paper:
            errors.append({"row":row,"record_id":record_id,"path":"paper_id","message":"unknown paper_id"}); continue
        for key in ("publication_date","provenance_url"):
            if pair.get(key) != paper.get(key):
                errors.append({"row":row,"record_id":record_id,"path":key,"message":"claim provenance must match paper registry"})
        source_ids={f"PMID:{paper['pmid']}" if paper.get("pmid") else None, paper.get("doi")}
        if pair.get("source_id") not in source_ids:
            errors.append({"row":row,"record_id":record_id,"path":"source_id","message":"claim source_id must match paper PMID or DOI"})
        span=pair.get("supporting_span",{})
        if span.get("end_char",0)-span.get("start_char",0) != len(span.get("text","")):
            errors.append({"row":row,"record_id":record_id,"path":"supporting_span","message":"span offsets must exactly match span text length"})
        source_path=pair.get("source_text_path")
        if source_path:
            try:
                source_file=manifest_file.parent / source_path
                source_text=source_file.read_text(encoding="utf-8")
                if sha256_file(source_file) != pair.get("source_text_sha256"):
                    errors.append({"row":row,"record_id":record_id,"path":"source_text_sha256","message":"source text checksum does not match local source"})
                if source_text[span.get("start_char",0):span.get("end_char",0)] != span.get("text"):
                    errors.append({"row":row,"record_id":record_id,"path":"supporting_span","message":"span text does not match local source offsets"})
            except OSError as exc:
                errors.append({"row":row,"record_id":record_id,"path":"source_text_path","message":str(exc)})
        if manifest.get("dataset_status") in {"gold", "silver"} and pair.get("review",{}).get("status") != "adjudicated":
            errors.append({"row":row,"record_id":record_id,"path":"review.status","message":"gold and silver claim/evidence pairs must be adjudicated"})
    return errors


def agreement_m2(records: Sequence[dict[str, Any]]) -> dict[str, float | int]:
    """Compute raw agreement and Cohen's kappa from paired M2 draft labels."""
    pairs: list[tuple[str, str]] = []
    for record in records:
        if record.get("task") != "m2":
            continue
        review = record.get("review", {})
        a = review.get("annotator_a", {}).get("label")
        b = review.get("annotator_b", {}).get("label")
        if a is None or b is None:
            continue
        if a not in M2_LABELS or b not in M2_LABELS:
            raise ValueError("M2 annotator labels must be supported, contradicted, or insufficient")
        pairs.append((a, b))
    if not pairs:
        raise ValueError("No paired M2 annotator labels")
    n = len(pairs)
    raw = sum(a == b for a, b in pairs) / n
    counts_a, counts_b = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum((counts_a[label] / n) * (counts_b[label] / n) for label in M2_LABELS)
    kappa = 1.0 if expected == 1.0 and raw == 1.0 else (raw - expected) / (1.0 - expected)
    return {"n_pairs": n, "raw_agreement": raw, "cohens_kappa": kappa}
