import json

from petlongevity_bench.io import load_json
from petlongevity_bench.llm_review import assemble_llm_review_submission, build_llm_review_prompts


def _packet(pair_id):
    return {
        "pair_id": pair_id,
        "paper_id": "PMID:1",
        "pmid": "1",
        "title": "Synthetic paper",
        "claim_text": "The intervention improved mobility.",
        "supporting_span": {"text": "The intervention improved mobility.", "start_char": 0, "end_char": 35},
        "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
        "machine_draft": {"label": "supported"},
    }


def test_build_llm_review_prompts_chunks_schema_and_strips_machine_drafts(tmp_path):
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    rows = [_packet("P1"), _packet("P2"), _packet("P3")]
    (review_dir / "reviewer_packet_blinded.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    manifest = build_llm_review_prompts(review_dir, tmp_path / "prompts", max_pairs_per_prompt=2, reviewer_id="fixture-llm")

    assert manifest["reviewer_slot"] == "llm_reviewer"
    assert manifest["n_pairs"] == 3
    assert manifest["n_chunks"] == 2
    assert [chunk["pairs"] for chunk in manifest["prompt_files"]] == [2, 1]

    schema = load_json(tmp_path / "prompts" / "response_schema.json")
    assert schema["properties"]["reviewer_id"]["const"] == "fixture-llm"
    assert set(schema["properties"]["label"]["enum"]) == {"contradicted", "insufficient", "supported"}

    prompt = (tmp_path / "prompts" / "chunk_001_prompt.md").read_text(encoding="utf-8")
    assert "machine_draft" not in prompt
    assert "Return exactly 2 JSONL rows" in prompt
    assert "petbench import-research-review" in prompt


def _decision(pair_id):
    return {
        "pair_id": pair_id,
        "reviewer_id": "fixture-llm",
        "label": "supported",
        "study_design": "controlled trial",
        "outcome": "mobility",
        "intervention_type": "diet",
        "evidence_strength": "moderate",
        "correlation_vs_causation": "causal",
        "protocol_vs_results": "results",
        "evidence_quote_verified": "yes",
        "notes": "The evidence text directly supports the claim.",
    }


def test_assemble_llm_review_submission_orders_and_validates_chunks(tmp_path):
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    (review_dir / "reviewer_packet_blinded.jsonl").write_text(
        "".join(json.dumps(_packet(pair_id)) + "\n" for pair_id in ("P1", "P2", "P3")),
        encoding="utf-8",
    )
    chunk_a = tmp_path / "chunk_a.jsonl"
    chunk_b = tmp_path / "chunk_b.jsonl"
    chunk_a.write_text(json.dumps(_decision("P2")) + "\n", encoding="utf-8")
    chunk_b.write_text(json.dumps(_decision("P1")) + "\n" + json.dumps(_decision("P3")) + "\n", encoding="utf-8")

    output = tmp_path / "llm_reviewer.jsonl"
    report = assemble_llm_review_submission([chunk_a, chunk_b], review_dir, output, reviewer_id="fixture-llm")

    assert report["valid"] is True
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["pair_id"] for row in lines] == ["P1", "P2", "P3"]


def test_assemble_llm_review_submission_rejects_duplicate_or_missing_pairs(tmp_path):
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    (review_dir / "reviewer_packet_blinded.jsonl").write_text(
        "".join(json.dumps(_packet(pair_id)) + "\n" for pair_id in ("P1", "P2")),
        encoding="utf-8",
    )
    response = tmp_path / "chunk.jsonl"
    response.write_text(json.dumps(_decision("P1")) + "\n" + json.dumps(_decision("P1")) + "\n", encoding="utf-8")

    output = tmp_path / "llm_reviewer.jsonl"
    report = assemble_llm_review_submission([response], review_dir, output, reviewer_id="fixture-llm")

    assert report["valid"] is False
    assert not output.exists()
    messages = {error["message"] for error in report["errors"]}
    assert "duplicate review pair" in messages
    assert "missing 1 review pairs" in messages
