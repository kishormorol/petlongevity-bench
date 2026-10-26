import json
from pathlib import Path

import pytest

from petlongevity_bench.io import load_json, load_jsonl
from petlongevity_bench.runner import run_offline, validate_run_manifest


BASE = Path(__file__).parents[1] / "data" / "demo"
PROMPT = Path(__file__).parents[1] / "prompts" / "M1_evidence_extraction.md"


def _paths(tmp_path):
    return tmp_path / "predictions.jsonl", tmp_path / "manifest.json", tmp_path / "responses.jsonl"


def test_b0_offline_reproduces_m1_fixture_and_writes_reproducible_artifacts(tmp_path):
    predictions, manifest, cache = _paths(tmp_path)
    result = run_offline("M1", "B0", BASE / "m1_gold.jsonl", BASE / "m1_pred_perfect.jsonl", predictions, manifest, cache, PROMPT, {"temperature": 0, "seed": 7}, run_date="2026-01-01")
    assert load_jsonl(predictions) == load_jsonl(BASE / "m1_pred_perfect.jsonl")
    assert len(load_jsonl(cache)) == 2
    assert result["baseline"] == "B0"
    assert result["source_snapshot_hash"] is None
    assert validate_run_manifest(load_json(manifest)) == []


def test_b1_requires_and_records_clean_frozen_snapshot(tmp_path):
    predictions, manifest, cache = _paths(tmp_path)
    result = run_offline("M1", "B1", BASE / "m1_gold.jsonl", BASE / "m1_pred_perfect.jsonl", predictions, manifest, cache, PROMPT, snapshot_manifest_path=BASE / "temporal_clean_manifest.json", run_date="2026-01-01")
    assert result["baseline"] == "B1"
    assert result["source_snapshot_hash"]
    assert result["temporal_leakage_status"] == "leakage_free"


def test_runner_rejects_missing_offline_prediction(tmp_path):
    partial = tmp_path / "partial.jsonl"
    partial.write_text(json.dumps(load_jsonl(BASE / "m1_pred_perfect.jsonl")[0]) + "\n", encoding="utf-8")
    predictions, manifest, cache = _paths(tmp_path)
    with pytest.raises(ValueError, match="missing offline predictions"):
        run_offline("M1", "B0", BASE / "m1_gold.jsonl", partial, predictions, manifest, cache, PROMPT)


def test_b1_rejects_missing_snapshot_and_secret_settings(tmp_path):
    predictions, manifest, cache = _paths(tmp_path)
    with pytest.raises(ValueError, match="requires a frozen snapshot"):
        run_offline("M1", "B1", BASE / "m1_gold.jsonl", BASE / "m1_pred_perfect.jsonl", predictions, manifest, cache, PROMPT)
    with pytest.raises(ValueError, match="must not contain secrets"):
        run_offline("M1", "B0", BASE / "m1_gold.jsonl", BASE / "m1_pred_perfect.jsonl", predictions, manifest, cache, PROMPT, {"api_key": "not-saved"})


def test_b1_rejects_leaky_snapshot_before_writing_artifacts(tmp_path):
    snapshot = json.loads((BASE / "temporal_clean_manifest.json").read_text(encoding="utf-8"))
    snapshot["effective_cutoff"] = "2015-12-31"
    snapshot["records_file"] = str(BASE / "temporal_clean_sources.jsonl")
    leaky_manifest = tmp_path / "leaky_snapshot.json"
    leaky_manifest.write_text(json.dumps(snapshot), encoding="utf-8")
    predictions, manifest, cache = _paths(tmp_path)
    with pytest.raises(ValueError, match="failed strict leakage audit"):
        run_offline("M1", "B1", BASE / "m1_gold.jsonl", BASE / "m1_pred_perfect.jsonl", predictions, manifest, cache, PROMPT, snapshot_manifest_path=leaky_manifest)
    assert not predictions.exists()
    assert not cache.exists()


def test_runner_rejects_malformed_m2_prediction(tmp_path):
    inputs = tmp_path / "inputs.jsonl"
    responses = tmp_path / "responses.jsonl"
    inputs.write_text('{"item_id":"J-1"}\n', encoding="utf-8")
    responses.write_text('{"item_id":"J-1","label":"unclear"}\n', encoding="utf-8")
    predictions, manifest, cache = _paths(tmp_path)
    with pytest.raises(ValueError, match="M2 prediction label"):
        run_offline("M2", "B0", inputs, responses, predictions, manifest, cache, PROMPT)
