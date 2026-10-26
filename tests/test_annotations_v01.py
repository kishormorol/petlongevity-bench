from __future__ import annotations

import csv
import json
from pathlib import Path

from petlongevity_bench.annotations_v01 import summary, validate_annotations, write_csv, write_queue
from petlongevity_bench.io import import_csv_jsonl, load_jsonl, write_jsonl


def _record(source: Path) -> dict:
    return {"annotation_id":"A-1","paper_id":"PMID:1","pmid":"1","doi":"10.1000/x","species":"dog","breed":None,"publication_date":"2020-01-01","study_design":"controlled trial","intervention":"test diet","intervention_type":"diet","comparator":"control","population":"dogs","sample_size":10,"outcome":"cognition","endpoint_type":"clinical","claim_text":"Finding occurred.","gold_label":"supported","evidence_strength":"moderate","causal_status":"causal_supported","species_transfer":"none","protocol_vs_result":"completed_result","evidence_quote":"Finding occurred.","evidence_section":"abstract","source_locator":str(source),"source_start_offset":0,"source_end_offset":17,"annotator_id":"machine","annotation_status":"draft","reviewer_id":None,"adjudication_notes":None,"confidence":0.5,"created_at":"2026-08-20T00:00:00Z","updated_at":"2026-08-20T00:00:00Z","generator_model":"test","generator_prompt_version":"test-v1"}


def _paths(tmp_path: Path, rows: list[dict]) -> tuple[Path, Path]:
    source=tmp_path/"source.txt"; source.write_text("Finding occurred.",encoding="utf-8")
    registry=tmp_path/"registry.jsonl"; annotations=tmp_path/"annotations.jsonl"
    write_jsonl(registry,[{"paper_id":"PMID:1","pmid":"1","doi":"10.1000/x","title":"Paper","publication_year":2020,"publication_date":"2020-01-01","species":["dog"],"provenance_url":"https://pubmed.ncbi.nlm.nih.gov/1/"}])
    write_jsonl(annotations,rows)
    return annotations,registry


def test_annotation_schema_and_source_quote_validation(tmp_path: Path):
    source=tmp_path/"source.txt"; source.write_text("Finding occurred.",encoding="utf-8")
    annotations,registry=_paths(tmp_path,[_record(source)])
    assert validate_annotations(annotations,registry)==[]
    row=load_jsonl(annotations)[0]; row["evidence_quote"]="invented"
    write_jsonl(annotations,[row])
    assert any(e["path"]=="evidence_quote" for e in validate_annotations(annotations,registry))
    row["evidence_quote"]=""; write_jsonl(annotations,[row])
    assert any(e["path"]=="evidence_quote" for e in validate_annotations(annotations,registry))


def test_causal_species_protocol_missing_and_duplicate_rejections(tmp_path: Path):
    source=tmp_path/"source.txt"; source.write_text("Finding occurred.",encoding="utf-8")
    row=_record(source); bad=dict(row); bad.update({"annotation_id":"A-1","study_design":"observational","causal_status":"causal_supported","species":"cat","protocol_vs_result":"completed_result"})
    annotations,registry=_paths(tmp_path,[row,bad])
    errors=validate_annotations(annotations,registry); messages={e["message"] for e in errors}
    assert "duplicate annotation_id" in messages
    assert "species conflicts with paper registry" in messages
    assert "observational evidence cannot be labeled causal_supported" in messages
    bad["study_design"]="protocol"; write_jsonl(annotations,[bad])
    assert any(e["message"]=="protocol cannot be completed efficacy evidence" for e in validate_annotations(annotations,registry))
    bad["paper_id"]="PMID:unknown"; write_jsonl(annotations,[bad])
    assert any(e["message"]=="unknown paper_id" for e in validate_annotations(annotations,registry))


def test_queue_summary_and_csv_round_trip(tmp_path: Path):
    source=tmp_path/"source.txt"; source.write_text("Finding occurred.",encoding="utf-8")
    one=_record(source); two=dict(one); two.update({"annotation_id":"A-2","gold_label":"insufficient","annotation_status":"adjudicated","confidence":0.95})
    counts=summary([one,two]); assert counts["requiring_adjudication"]==1 and counts["gold_label"]=={"insufficient":1,"supported":1}
    queue=tmp_path/"queue.csv"; write_queue([one,two],queue)
    assert len(list(csv.DictReader(queue.open())))==1
    jsonl=tmp_path/"annotations.jsonl"; csv_path=tmp_path/"annotations.csv"; recovered=tmp_path/"recovered.jsonl"
    write_jsonl(jsonl,[one,two]); write_csv([one,two],csv_path); import_csv_jsonl(csv_path,recovered)
    assert load_jsonl(recovered)==[one,two]
