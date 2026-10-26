import json

from petlongevity_bench.datasets import validate_research_dataset
from petlongevity_bench.io import export_jsonl_csv, import_csv_jsonl, load_jsonl


def _paper():
    return {"paper_id":"PMID:123","pmid":"123","doi":None,"title":"Registry test paper","publication_year":2020,"publication_date":"2020-01-02","species":["dog"],"provenance_url":"https://pubmed.ncbi.nlm.nih.gov/123/"}


def _pair(status="adjudicated"):
    return {"pair_id":"CE-1","paper_id":"PMID:123","claim_id":"C-1","claim_text":"A registry test claim.","source_id":"PMID:123","publication_date":"2020-01-02","provenance_url":"https://pubmed.ncbi.nlm.nih.gov/123/","source_text_sha256":"a"*64,"supporting_span":{"text":"Exact span.","start_char":10,"end_char":21},"species":["dog"],"study_design":"controlled trial","outcome":"mobility","intervention_type":"diet","evidence_strength":"moderate","label":"supported","correlation_vs_causation":"causal","protocol_vs_results":"results","review":{"annotator_a":{"annotator_id":"a"},"annotator_b":{"annotator_id":"b"},"adjudicator":{"annotator_id":"c"},"status":status,"notes":None}}


def _write(tmp_path,paper=None,pair=None,status="gold"):
    papers=tmp_path/"papers.jsonl"; pairs=tmp_path/"pairs.jsonl"; manifest=tmp_path/"manifest.json"
    papers.write_text(json.dumps(paper or _paper())+"\n",encoding="utf-8")
    pairs.write_text(json.dumps(pair or _pair())+"\n",encoding="utf-8")
    manifest.write_text(json.dumps({"dataset_id":"research-test","schema_version":"1.0","dataset_status":status,"paper_registry_file":papers.name,"claim_evidence_file":pairs.name,"description":"schema fixture","license":"CC0"}),encoding="utf-8")
    return manifest,papers,pairs


def test_research_dataset_accepts_registry_linked_adjudicated_pair(tmp_path):
    assert validate_research_dataset(_write(tmp_path)[0]) == []


def test_research_dataset_rejects_invalid_date_and_provenance_url(tmp_path):
    paper=_paper(); paper["publication_date"]="not-a-date"; paper["provenance_url"]="not a url"
    errors=validate_research_dataset(_write(tmp_path,paper=paper)[0])
    assert any("not-a-date" in error["message"] or "not a url" in error["message"] for error in errors)


def test_research_dataset_requires_exact_span_and_registry_provenance(tmp_path):
    pair=_pair(); pair["source_id"]="PMID:999"; pair["supporting_span"]["end_char"]=20
    errors=validate_research_dataset(_write(tmp_path,pair=pair)[0])
    assert {error["path"] for error in errors} >= {"source_id","supporting_span"}


def test_research_gold_rejects_draft_but_draft_dataset_allows_it(tmp_path):
    pair=_pair("draft")
    assert any(error["path"]=="review.status" for error in validate_research_dataset(_write(tmp_path,pair=pair,status="gold")[0]))
    assert validate_research_dataset(_write(tmp_path,pair=pair,status="draft")[0]) == []


def test_jsonl_csv_round_trip_preserves_nested_claim_fields(tmp_path):
    _,papers,pairs=_write(tmp_path)
    csv_path=tmp_path/"pairs.csv"; imported=tmp_path/"imported.jsonl"
    export_jsonl_csv(pairs,csv_path); import_csv_jsonl(csv_path,imported)
    assert load_jsonl(imported)==load_jsonl(pairs)
    papers_csv=tmp_path/"papers.csv"; imported_papers=tmp_path/"imported_papers.jsonl"
    export_jsonl_csv(papers,papers_csv); import_csv_jsonl(papers_csv,imported_papers)
    assert load_jsonl(imported_papers)==load_jsonl(papers)


def test_research_dataset_validates_local_source_checksum_and_span(tmp_path):
    manifest, _, pairs = _write(tmp_path, status="draft")
    source = tmp_path / "source.txt"
    source.write_text("012Exact span.9", encoding="utf-8")
    pair = load_jsonl(pairs)[0]
    import hashlib
    pair["source_text_path"] = source.name
    pair["source_text_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    pair["supporting_span"] = {"text":"Exact span.", "start_char":3, "end_char":14}
    pairs.write_text(json.dumps(pair) + "\n", encoding="utf-8")
    assert validate_research_dataset(manifest) == []
    pair["supporting_span"]["text"] = "Wrong span."
    pairs.write_text(json.dumps(pair) + "\n", encoding="utf-8")
    assert any(error["path"] == "supporting_span" for error in validate_research_dataset(manifest))
