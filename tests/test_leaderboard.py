from __future__ import annotations

import json
import pytest
from petlongevity_bench.leaderboard import build_leaderboard, load_submissions


def _submission(**changes):
    row = {"submission_id":"run-1","system_name":"Retriever","system_version":"abc123","baseline":"B1","modules":["M1","M2"],"primary_metric":"macro_f1","primary_score":0.72,"dataset_version":"v0.1","run_manifest_sha256":"a" * 64,"evaluated_at":"2026-08-20T00:00:00Z","status":"verified"}
    row.update(changes)
    return row


def test_build_leaderboard_renders_verified_and_pending_entries(tmp_path):
    submissions = tmp_path / "submissions.jsonl"
    submissions.write_text("\n".join(json.dumps(row) for row in [_submission(), _submission(submission_id="run-2", system_name="Candidate", status="pending", primary_score=0.99)]) + "\n", encoding="utf-8")
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"total_annotations":75,"double_reviewed_count":2,"adjudicated_count":1}), encoding="utf-8")
    output = tmp_path / "index.html"
    report = build_leaderboard(submissions, status, output)
    html = output.read_text(encoding="utf-8")
    assert report == {"submissions":2,"verified":1}
    assert "Retriever" in html and "Candidate" in html
    assert "2 / 75" in html and "What makes a result publishable" in html
    assert "Scope integrity map" in html and "Adversarial scope tests" in html
    assert "Scope firewall active" in html and "Time-frozen" in html


def test_load_submissions_rejects_untraceable_submission(tmp_path):
    submissions = tmp_path / "submissions.jsonl"
    submissions.write_text(json.dumps(_submission(run_manifest_sha256="short")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        load_submissions(submissions)
