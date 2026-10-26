import json
from pathlib import Path

import pytest

from petlongevity_bench.agent import ToolResult, run_b3_offline
from petlongevity_bench.io import load_jsonl
from petlongevity_bench.metrics import score_m2


BASE = Path(__file__).parents[1] / "data" / "demo"
PROMPT = Path(__file__).parents[1] / "prompts" / "M2_evidence_judgment.md"


def _paths(tmp_path):
    return tmp_path / "predictions.jsonl", tmp_path / "manifest.json", tmp_path / "trace.jsonl"


def _run(tmp_path, responses=None, tools=None):
    predictions, manifest, trace = _paths(tmp_path)
    return run_b3_offline("M2", BASE / "m2_gold.jsonl", responses or BASE / "b3_m2_responses.jsonl", predictions, manifest, trace, PROMPT, BASE / "temporal_clean_manifest.json", BASE / "kg_nodes.jsonl", BASE / "kg_edges.jsonl", "I:demo", "cat", tools=tools, run_date="2026-01-01"), predictions, trace


def test_b3_outputs_are_scored_by_the_same_m2_evaluator(tmp_path):
    _, predictions, trace = _run(tmp_path)
    gold = load_jsonl(BASE / "m2_gold.jsonl")
    assert score_m2(gold, load_jsonl(predictions)) == score_m2(gold, load_jsonl(BASE / "m2_pred_perfect.jsonl"))
    assert all(row["status"] == "success" for row in load_jsonl(trace))


def test_b3_rejects_supported_claim_without_available_evidence(tmp_path):
    rows = load_jsonl(BASE / "b3_m2_responses.jsonl")
    rows[0]["claims"][0]["evidence_ids"] = ["E:missing"]
    responses = tmp_path / "unsupported.jsonl"
    responses.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(ValueError, match="claim_cites_unavailable_evidence"):
        _run(tmp_path, responses)


def test_b3_tool_failure_is_saved_and_cannot_support_claims(tmp_path):
    class BrokenTool:
        name = "broken"

        def execute(self):
            raise RuntimeError("offline tool failure")

    with pytest.raises(ValueError, match="tool_failure_requires_uncertainty"):
        _run(tmp_path, tools=[BrokenTool()])
    assert load_jsonl(tmp_path / "trace.jsonl") == [{"tool_name": "broken", "status": "failure", "evidence_ids": [], "error": "offline tool failure"}]


def test_b3_allows_explicitly_unsupported_claim_after_tool_failure(tmp_path):
    rows = load_jsonl(BASE / "b3_m2_responses.jsonl")
    for row in rows:
        row["claims"][0]["status"] = "unsupported"
        row["claims"][0]["evidence_ids"] = []
    responses = tmp_path / "uncertain.jsonl"
    responses.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    class BrokenTool:
        name = "broken"

        def execute(self):
            raise RuntimeError("offline tool failure")

    _, predictions, _ = _run(tmp_path, responses, [BrokenTool()])
    assert len(load_jsonl(predictions)) == 4


def test_b3_redacts_secret_like_tool_error_text(tmp_path):
    class BrokenTool:
        name = "broken"

        def execute(self):
            raise RuntimeError("token=do-not-save")

    with pytest.raises(ValueError):
        _run(tmp_path, tools=[BrokenTool()])
    assert "do-not-save" not in (tmp_path / "trace.jsonl").read_text(encoding="utf-8")
