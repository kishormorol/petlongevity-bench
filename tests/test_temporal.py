import json

from petlongevity_bench.temporal import audit_snapshot, freeze_snapshot


REGISTRY = [{"name": "PubMed", "kind": "database", "version": "2020-baseline", "effective_date": "2020-01-01", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/"}]


def _freeze(tmp_path, rows):
    records = tmp_path / "records.jsonl"
    records.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    manifest = tmp_path / "snapshot.json"
    frozen = freeze_snapshot(records, manifest, "test-snapshot", "test-source", "dog aging", "2020-12-31", REGISTRY, "2021-01-01")
    return records, manifest, frozen


def test_clean_snapshot_is_leakage_free_and_hash_is_stable(tmp_path):
    rows = [{"source_id": "PMID:1", "publication_date": "2020-01-01", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/1/"}]
    _, manifest, first = _freeze(tmp_path, rows)
    _, _, second = _freeze(tmp_path, rows)
    assert first["records_sha256"] == second["records_sha256"]
    assert first["records_content_sha256"] == second["records_content_sha256"]
    assert audit_snapshot(manifest)["leakage_free"]


def test_post_cutoff_source_fails_strict_audit(tmp_path):
    _, manifest, _ = _freeze(tmp_path, [{"source_id": "PMID:2", "effective_date": "2021-01-01", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/2/"}])
    report = audit_snapshot(manifest)
    assert not report["leakage_free"]
    assert report["post_cutoff_leakage_detected"]


def test_undated_source_fails_strict_but_not_non_strict_audit(tmp_path):
    _, manifest, _ = _freeze(tmp_path, [{"source_id": "PMID:3", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/3/"}])
    assert not audit_snapshot(manifest, strict=True)["leakage_free"]
    assert audit_snapshot(manifest, strict=False)["leakage_free"]


def test_prompt_with_post_cutoff_date_fails_audit(tmp_path):
    _, manifest, _ = _freeze(tmp_path, [{"source_id": "PMID:4", "publication_date": "2020-01-01", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/4/"}])
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Do not rely on 2021-01-01 evidence.", encoding="utf-8")
    assert not audit_snapshot(manifest, prompt_path=prompt)["leakage_free"]


def test_prompt_with_known_post_cutoff_source_anchor_fails_audit(tmp_path):
    _, manifest, _ = _freeze(tmp_path, [{"source_id": "PMID:42", "publication_date": "2021-01-01", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/42/"}])
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Use PMID:42 as supporting context.", encoding="utf-8")
    report = audit_snapshot(manifest, prompt_path=prompt)
    assert any(issue["kind"] == "post_cutoff_prompt_source_anchor" for issue in report["issues"])


def test_modified_snapshot_records_fail_hash_audit(tmp_path):
    records, manifest, _ = _freeze(tmp_path, [{"source_id": "PMID:5", "publication_date": "2020-01-01", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/5/"}])
    records.write_text(json.dumps({"source_id": "PMID:5", "publication_date": "2020-01-02", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/5/"}) + "\n", encoding="utf-8")
    assert any(issue["kind"] == "records_hash_mismatch" for issue in audit_snapshot(manifest)["issues"])


def test_invalid_cutoff_fails_without_reporting_snapshot_clean(tmp_path):
    _, manifest, _ = _freeze(tmp_path, [{"source_id": "PMID:6", "publication_date": "2020-01-01", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/6/"}])
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["effective_cutoff"] = "not-a-date"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    report = audit_snapshot(manifest)
    assert not report["leakage_free"]
    assert any(issue["kind"] == "invalid_cutoff" for issue in report["issues"])
