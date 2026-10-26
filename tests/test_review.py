from __future__ import annotations

from pathlib import Path

import pytest

from petlongevity_bench.io import load_jsonl, write_jsonl
from petlongevity_bench.review import adjudicate, build_adjudication_queue, freeze_gate, import_review, prepare_review


def _annotation(identifier: str, source: Path) -> dict:
    return {"annotation_id":identifier,"paper_id":"PMID:1","pmid":"1","doi":"10.1/x","species":"dog","breed":None,"publication_date":"2020-01-01","study_design":"controlled trial","intervention":"diet","intervention_type":"diet","comparator":"control","population":"dogs","sample_size":2,"outcome":"cognition","endpoint_type":"clinical","claim_text":"Claim","gold_label":"supported","causal_status":"causal_supported","species_transfer":"none","protocol_vs_result":"completed_result","evidence_strength":"moderate","evidence_quote":"Evidence.","evidence_section":"abstract","source_locator":str(source),"source_start_offset":0,"source_end_offset":9,"annotator_id":"machine","annotation_status":"draft","reviewer_id":None,"adjudication_notes":None,"confidence":0.5,"created_at":"2026-08-20T00:00:00Z","updated_at":"2026-08-20T00:00:00Z","generator_model":"test","generator_prompt_version":"test-v1"}


def _decision(identifier: str, label: str="supported") -> dict:
    return {"annotation_id":identifier,"reviewer_id":"reviewer","label_decision":label,"species_decision":"dog","study_design_decision":"controlled trial","causal_status_decision":"causal_supported","protocol_vs_result_decision":"completed_result","evidence_strength_decision":"moderate","evidence_quote_verified":"yes","source_support_quality":"direct","reviewer_confidence":0.9,"reviewer_notes":"checked","review_timestamp":"2026-08-20T00:00:00Z"}


def _workspace(tmp_path: Path) -> tuple[Path,Path,Path]:
    source=tmp_path/"source.txt"; source.write_text("Evidence.",encoding="utf-8")
    annotations=tmp_path/"annotations.jsonl"; registry=tmp_path/"registry.jsonl"; review=tmp_path/"review"
    write_jsonl(annotations,[_annotation("A1",source),_annotation("A2",source)])
    write_jsonl(registry,[{"paper_id":"PMID:1","pmid":"1","doi":"10.1/x","title":"Paper","publication_year":2020,"publication_date":"2020-01-01","species":["dog"],"provenance_url":"https://pubmed.ncbi.nlm.nih.gov/1/"}])
    prepare_review(annotations,registry,review)
    return annotations,registry,review


def test_reviewer_independence_and_import(tmp_path: Path):
    annotations,_,review=_workspace(tmp_path)
    packet=load_jsonl(review/"reviewer_packet.jsonl")[0]
    assert "reviewer_1" not in packet and "label_decision" not in packet
    guidelines=(review/"reviewer_guidelines.md").read_text(encoding="utf-8")
    assert "does not ask you to recommend treatment" in guidelines
    assert "Supported" in guidelines and "Contradicted" in guidelines and "Insufficient" in guidelines
    r1=tmp_path/"r1.jsonl"; write_jsonl(r1,[_decision("A1"),_decision("A2")])
    import_review(r1,"reviewer_1",annotations,review)
    with pytest.raises(ValueError,match="already exists"): import_review(r1,"reviewer_1",annotations,review)
    r2=tmp_path/"r2.jsonl"; write_jsonl(r2,[_decision("A1"),_decision("A2")])
    import_review(r2,"reviewer_2",annotations,review)
    assert len(load_jsonl(review/"reviews"/"reviewer_1.jsonl"))==2


def test_disagreement_adjudication_audit_trail_and_freeze_gate(tmp_path: Path):
    annotations,registry,review=_workspace(tmp_path)
    r1=tmp_path/"r1.jsonl"; r2=tmp_path/"r2.jsonl"; write_jsonl(r1,[_decision("A1"),_decision("A2")]); write_jsonl(r2,[_decision("A1","contradicted"),_decision("A2")])
    assert freeze_gate(annotations,review,registry)["READY_TO_FREEZE"] is False
    import_review(r1,"reviewer_1",annotations,review); before=(review/"reviews"/"reviewer_1.jsonl").read_text()
    import_review(r2,"reviewer_2",annotations,review); conflicts=build_adjudication_queue(annotations,review)
    assert [row["annotation_id"] for row in conflicts]==["A1"]
    adjudications=tmp_path/"adjudications.jsonl"; write_jsonl(adjudications,[{"annotation_id":"A1","adjudicator_id":"adjudicator","final_gold_label":"supported","final_species":"dog","final_study_design":"controlled trial","final_causal_status":"causal_supported","final_protocol_vs_result":"completed_result","final_evidence_strength":"moderate","final_evidence_quote_verified":"yes","adjudication_notes":"resolved","final_confidence":0.9,"adjudicated_at":"2026-08-20T00:00:00Z"}])
    status=adjudicate(adjudications,annotations,review)
    assert status["disagreement_count"]==1 and (review/"reviews"/"reviewer_1.jsonl").read_text()==before
    assert freeze_gate(annotations,review,registry)["READY_TO_FREEZE"] is True
    assert status["agreement"]["label_decision"]["raw_agreement"]==0.5
