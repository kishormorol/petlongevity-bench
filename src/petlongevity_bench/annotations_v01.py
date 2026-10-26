"""Validation and reports for the draft scientific-annotation dataset v0.1."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .io import load_jsonl, sha256_file
from .schema import validate_records

SCHEMA = Path(__file__).parents[2] / "schemas" / "scientific_annotation_v01_schema.json"


def validate_annotations(path: str | Path, registry_path: str | Path) -> list[dict[str, Any]]:
    """Return schema and source-integrity errors for v0.1 annotation records."""
    file=Path(path); rows=load_jsonl(file); registry={r["paper_id"]:r for r in load_jsonl(registry_path)}
    errors=validate_records(rows, SCHEMA); seen:set[str]=set()
    for row, item in enumerate(rows):
        ident=item.get("annotation_id")
        if ident in seen: errors.append({"row":row,"record_id":ident,"path":"annotation_id","message":"duplicate annotation_id"})
        seen.add(ident)
        paper=registry.get(item.get("paper_id"))
        if not paper:
            errors.append({"row":row,"record_id":ident,"path":"paper_id","message":"unknown paper_id"}); continue
        for key in ("pmid", "doi", "publication_date"):
            if item.get(key) != paper.get(key): errors.append({"row":row,"record_id":ident,"path":key,"message":"annotation provenance must match paper registry"})
        if item.get("species") not in paper.get("species",[]): errors.append({"row":row,"record_id":ident,"path":"species","message":"species conflicts with paper registry"})
        if item.get("gold_label") in {"supported","contradicted"} and not item.get("evidence_quote"):
            errors.append({"row":row,"record_id":ident,"path":"evidence_quote","message":"evidence quote is required"})
        if not item.get("source_locator"): errors.append({"row":row,"record_id":ident,"path":"source_locator","message":"source locator is required"})
        if item.get("causal_status")=="causal_supported" and item.get("study_design") in {"observational","cohort","review"}:
            errors.append({"row":row,"record_id":ident,"path":"causal_status","message":"observational evidence cannot be labeled causal_supported"})
        if item.get("study_design")=="protocol" and item.get("protocol_vs_result")=="completed_result":
            errors.append({"row":row,"record_id":ident,"path":"protocol_vs_result","message":"protocol cannot be completed efficacy evidence"})
        locator=Path(item.get("source_locator",""))
        if locator.exists():
            source=locator.read_text(encoding="utf-8"); start=item.get("source_start_offset",0); end=item.get("source_end_offset",0)
            if source[start:end] != item.get("evidence_quote"):
                errors.append({"row":row,"record_id":ident,"path":"evidence_quote","message":"quote cannot be located at source offsets"})
    return errors


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce deterministic label/species/study-design counts for release reports."""
    return {"total_annotations":len(rows), "gold_label":dict(sorted(Counter(r["gold_label"] for r in rows).items())), "species":dict(sorted(Counter(r["species"] for r in rows).items())), "study_design":dict(sorted(Counter(r["study_design"] for r in rows).items())), "requiring_adjudication":sum(r["annotation_status"]!="adjudicated" or r["confidence"]<0.90 for r in rows)}


def write_csv(rows: list[dict[str, Any]], destination: str | Path) -> None:
    with open(destination,"w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]) if rows else []); writer.writeheader()
        for row in rows:
            writer.writerow({key:json.dumps(value,ensure_ascii=False,sort_keys=True) for key,value in row.items()})


def write_queue(rows: list[dict[str, Any]], destination: str | Path) -> None:
    selected=[r for r in rows if r["annotation_status"]!="adjudicated" or r["confidence"]<0.90]
    write_csv(selected,destination)
