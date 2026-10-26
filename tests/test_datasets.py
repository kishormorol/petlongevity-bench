import json

from petlongevity_bench.datasets import agreement_m2, validate_dataset


def _record(label_a="supported", label_b="supported", status="adjudicated"):
    return {
        "annotation_id": "A-1",
        "task": "m2",
        "source": {"source_id": "PMID:123", "source_id_type": "pmid", "publication_date": "2020-01-01", "provenance_url": "https://pubmed.ncbi.nlm.nih.gov/123/"},
        "review": {
            "annotator_a": {"annotator_id": "a", "label": label_a},
            "annotator_b": {"annotator_id": "b", "label": label_b},
            "adjudicator": {"annotator_id": "c"},
            "status": status,
            "notes": None,
        },
        "claim_judgment": {"item_id": "J-1", "claim": "A claim", "evidence_ids": ["PMID:123"], "label": "supported"},
    }


def _write_dataset(tmp_path, record, status="gold"):
    records = tmp_path / "records.jsonl"
    records.write_text(json.dumps(record) + "\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"dataset_id": "test", "schema_version": "1.0", "task": "m2", "dataset_status": status, "records_file": records.name, "description": "test fixture", "license": "CC0"}), encoding="utf-8")
    return manifest


def test_validate_dataset_accepts_adjudicated_gold_record(tmp_path):
    assert validate_dataset(_write_dataset(tmp_path, _record())) == []


def test_validate_dataset_accepts_adjudicated_m1_gold_record(tmp_path):
    record = _record()
    record["task"] = "m1"
    del record["claim_judgment"]
    record["evidence"] = {
        "record_id": "M1-1", "species": ["dog"], "study_type": "controlled_trial",
        "intervention_or_exposure": "candidate diet", "endpoint": "mobility",
        "result_direction": "beneficial", "evidence_tier": "T4",
        "direct_species_evidence": True, "efficacy_result": True,
        "supporting_span": "Prespecified mobility improved.",
    }
    manifest = _write_dataset(tmp_path, record)
    manifest.write_text(json.dumps({"dataset_id": "test", "schema_version": "1.0", "task": "m1", "dataset_status": "gold", "records_file": "records.jsonl", "description": "test fixture", "license": "CC0"}), encoding="utf-8")
    assert validate_dataset(manifest) == []


def test_validate_dataset_rejects_missing_provenance(tmp_path):
    record = _record()
    del record["source"]["provenance_url"]
    errors = validate_dataset(_write_dataset(tmp_path, record))
    assert any(error["path"] == "source" and "provenance_url" in error["message"] for error in errors)


def test_validate_dataset_rejects_malformed_date_and_provenance_url(tmp_path):
    record = _record()
    record["source"]["publication_date"] = "not-a-date"
    record["source"]["provenance_url"] = "not a url"
    errors = validate_dataset(_write_dataset(tmp_path, record))
    assert any(error["path"] == "source.publication_date" for error in errors)
    assert any(error["path"] == "source.provenance_url" for error in errors)


def test_validate_dataset_rejects_unadjudicated_gold_but_allows_draft(tmp_path):
    record = _record(status="draft")
    assert any(error["path"] == "review.status" for error in validate_dataset(_write_dataset(tmp_path, record, "gold")))
    assert validate_dataset(_write_dataset(tmp_path, record, "draft")) == []


def test_agreement_m2_perfect_agreement():
    rows = [_record("supported", "supported"), _record("contradicted", "contradicted"), _record("insufficient", "insufficient")]
    result = agreement_m2(rows)
    assert result == {"n_pairs": 3, "raw_agreement": 1.0, "cohens_kappa": 1.0}


def test_agreement_m2_partial_agreement():
    rows = [_record("supported", "supported"), _record("contradicted", "insufficient"), _record("insufficient", "insufficient")]
    result = agreement_m2(rows)
    assert result["n_pairs"] == 3
    assert result["raw_agreement"] == 2 / 3
    assert 0 < result["cohens_kappa"] < 1


def test_agreement_m2_complete_disagreement_edge_case():
    result = agreement_m2([_record("supported", "contradicted")])
    assert result == {"n_pairs": 1, "raw_agreement": 0.0, "cohens_kappa": 0.0}
