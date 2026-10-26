import json

from petlongevity_bench.io import load_json, load_jsonl
from petlongevity_bench.datasets import validate_research_dataset
from petlongevity_bench.research_review import (
    adjudicate_llm_review,
    adjudicate_research_review,
    build_llm_adjudication_queue,
    build_research_adjudication_queue,
    export_m2_baseline_splits,
    import_research_review,
    llm_review_status,
    prepare_research_review,
    promote_research_gold,
    promote_research_silver,
    research_review_status,
    validate_llm_adjudication_submission,
    validate_research_review_submission,
)


def _paper(pmid):
    return {
        "paper_id": f"PMID:{pmid}",
        "pmid": str(pmid),
        "doi": None,
        "title": f"Review test paper {pmid}",
        "publication_year": 2020,
        "publication_date": "2020-01-02",
        "species": ["cat"],
        "provenance_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def _pair(pmid, number):
    return {
        "pair_id": f"{pmid}-A{number}",
        "paper_id": f"PMID:{pmid}",
        "claim_id": f"{pmid}-C{number}",
        "claim_text": "Cats with the measured marker had shorter survival.",
        "source_id": f"PMID:{pmid}",
        "publication_date": "2020-01-02",
        "provenance_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "source_text_sha256": "a" * 64,
        "supporting_span": {"text": "Cats with the measured marker had shorter survival.", "start_char": 0, "end_char": 51},
        "species": ["cat"],
        "study_design": "observational",
        "outcome": "mortality",
        "intervention_type": "biomarker-only",
        "evidence_strength": "low",
        "label": "supported",
        "correlation_vs_causation": "correlational",
        "protocol_vs_results": "results",
        "review": {
            "annotator_a": {"annotator_id": "automated-draft-extraction"},
            "annotator_b": {"annotator_id": "unassigned"},
            "adjudicator": {"annotator_id": "unassigned"},
            "status": "draft",
            "notes": "draft",
        },
    }


def _write_manifest(tmp_path):
    papers = [_paper(100), _paper(200), _paper(300), _paper(400)]
    pairs = [_pair(paper["pmid"], i) for paper in papers for i in (1, 2, 3)]
    (tmp_path / "paper_registry.jsonl").write_text("".join(json.dumps(row) + "\n" for row in papers), encoding="utf-8")
    (tmp_path / "claim_evidence.jsonl").write_text("".join(json.dumps(row) + "\n" for row in pairs), encoding="utf-8")
    manifest = {
        "dataset_id": "review-test",
        "schema_version": "1.0",
        "dataset_status": "draft",
        "paper_registry_file": "paper_registry.jsonl",
        "claim_evidence_file": "claim_evidence.jsonl",
        "description": "fixture",
        "license": "CC0",
    }
    path = tmp_path / "research_dataset_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    corpus = tmp_path / "corpus_registry.jsonl"
    corpus.write_text(
        "".join(
            json.dumps({"paper_id": paper["paper_id"], "target_category": "cat_ckd_survival", "full_text_available": paper["pmid"] in {"100", "200"}}) + "\n"
            for paper in papers
        ),
        encoding="utf-8",
    )
    return path, corpus


def _decision(pair_id, reviewer_id="reviewer"):
    return {
        "pair_id": pair_id,
        "reviewer_id": reviewer_id,
        "label": "supported",
        "study_design": "observational",
        "outcome": "mortality",
        "intervention_type": "biomarker-only",
        "evidence_strength": "low",
        "correlation_vs_causation": "correlational",
        "protocol_vs_results": "results",
        "evidence_quote_verified": "yes",
        "notes": "synthetic review decision",
    }


def _write_submission(path, pair_ids, reviewer_id, conflicts=False):
    rows = []
    for index, pair_id in enumerate(pair_ids):
        row = _decision(pair_id, reviewer_id)
        if conflicts and index == 0:
            row["label"] = "insufficient"
            row["evidence_strength"] = "very_low"
        rows.append(row)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_prepare_research_review_writes_blinded_packets_dashboard_and_splits(tmp_path):
    manifest, corpus = _write_manifest(tmp_path)
    report = prepare_research_review(manifest, tmp_path / "review", corpus_registry_path=corpus, split_seed="fixed")
    assert report["pairs"] == 12
    assert report["validation_errors"] == 0

    blinded = load_jsonl(tmp_path / "review" / "reviewer_packet_blinded.jsonl")
    coordinator = load_jsonl(tmp_path / "review" / "coordinator_packet.jsonl")
    assert "machine_draft" not in blinded[0]
    assert coordinator[0]["machine_draft"]["label"] == "supported"

    split_manifest = load_json(tmp_path / "review" / "splits.json")
    split_papers = [paper_id for ids in split_manifest["splits"].values() for paper_id in ids]
    assert sorted(split_papers) == ["PMID:100", "PMID:200", "PMID:300", "PMID:400"]
    for split in ("draft_train", "draft_dev", "hidden_test_candidate"):
        rows = load_jsonl(tmp_path / "review" / "splits" / f"{split}.jsonl")
        assert len(rows) % 3 == 0

    dashboard = load_json(tmp_path / "review" / "quality_dashboard.json")
    assert dashboard["full_text_available_papers"] == 2
    assert dashboard["papers_by_target_category"] == {"cat_ckd_survival": 4}


def test_research_review_status_counts_conflicts_and_adjudication(tmp_path):
    manifest, corpus = _write_manifest(tmp_path)
    prepare_research_review(manifest, tmp_path / "review", corpus_registry_path=corpus)
    a = {"pair_id": "100-A1", "label": "supported"}
    b = {"pair_id": "100-A1", "label": "contradicted"}
    adj = {"pair_id": "100-A1", "label": "supported"}
    (tmp_path / "review" / "reviewer_a.jsonl").write_text(json.dumps(a) + "\n", encoding="utf-8")
    (tmp_path / "review" / "reviewer_b.jsonl").write_text(json.dumps(b) + "\n", encoding="utf-8")
    status = research_review_status(tmp_path / "review")
    assert status["conflicts"] == 1
    assert status["missing_adjudication"] == 1
    (tmp_path / "review" / "adjudications.jsonl").write_text(json.dumps(adj) + "\n", encoding="utf-8")
    status = research_review_status(tmp_path / "review")
    assert status["adjudicated_conflicts"] == 1


def test_research_review_import_adjudicate_promote_and_export_m2_splits(tmp_path):
    manifest, corpus = _write_manifest(tmp_path)
    prepare_research_review(manifest, tmp_path / "review", corpus_registry_path=corpus, split_seed="fixed")
    pair_ids = [row["pair_id"] for row in load_jsonl(tmp_path / "review" / "coordinator_packet.jsonl")]
    reviewer_a = _write_submission(tmp_path / "reviewer_a_submission.jsonl", pair_ids, "reviewer-a")
    reviewer_b = _write_submission(tmp_path / "reviewer_b_submission.jsonl", pair_ids, "reviewer-b", conflicts=True)

    assert validate_research_review_submission(reviewer_a, tmp_path / "review") == []
    import_research_review(reviewer_a, "reviewer_a", tmp_path / "review")
    status = import_research_review(reviewer_b, "reviewer_b", tmp_path / "review")
    assert status["conflicts"] == 1
    assert status["READY_TO_FREEZE"] is False

    conflicts = build_research_adjudication_queue(tmp_path / "review")
    assert len(conflicts) == 1
    adjudication = {
        "pair_id": conflicts[0]["pair_id"],
        "adjudicator_id": "adjudicator",
        "final_label": "supported",
        "final_study_design": "observational",
        "final_outcome": "mortality",
        "final_intervention_type": "biomarker-only",
        "final_evidence_strength": "low",
        "final_correlation_vs_causation": "correlational",
        "final_protocol_vs_results": "results",
        "final_evidence_quote_verified": "yes",
        "adjudication_notes": "resolved synthetic disagreement",
        "adjudicated_at": "2026-08-30T00:00:00Z",
    }
    (tmp_path / "adjudication.jsonl").write_text(json.dumps(adjudication) + "\n", encoding="utf-8")
    status = adjudicate_research_review(tmp_path / "adjudication.jsonl", tmp_path / "review")
    assert status["READY_TO_FREEZE"] is True

    report = promote_research_gold(manifest, tmp_path / "review", tmp_path / "gold", dataset_id="fixture-gold")
    assert report["pairs"] == 12
    gold_manifest = load_json(tmp_path / "gold" / "research_dataset_manifest.json")
    assert gold_manifest["dataset_status"] == "gold"
    gold_pairs = load_jsonl(tmp_path / "gold" / "claim_evidence.jsonl")
    assert all(pair["review"]["status"] == "adjudicated" for pair in gold_pairs)

    split_report = export_m2_baseline_splits(tmp_path / "gold" / "claim_evidence.jsonl", tmp_path / "review" / "splits.json", tmp_path / "m2")
    assert sum(split_report["splits"].values()) == 12
    assert load_jsonl(tmp_path / "m2" / "draft_train_m2_gold.jsonl")[0]["item_id"].endswith("-A1")


def test_research_gold_promotion_requires_complete_human_reviews(tmp_path):
    manifest, corpus = _write_manifest(tmp_path)
    prepare_research_review(manifest, tmp_path / "review", corpus_registry_path=corpus)
    try:
        promote_research_gold(manifest, tmp_path / "review", tmp_path / "gold")
    except ValueError as exc:
        assert "not ready" in str(exc)
    else:
        raise AssertionError("promotion should require completed reviews")


def test_llm_review_promotes_silver_but_not_gold(tmp_path):
    manifest, corpus = _write_manifest(tmp_path)
    prepare_research_review(manifest, tmp_path / "review", corpus_registry_path=corpus, split_seed="fixed")
    pair_ids = [row["pair_id"] for row in load_jsonl(tmp_path / "review" / "coordinator_packet.jsonl")]
    reviewer_a = _write_submission(tmp_path / "reviewer_a_submission.jsonl", pair_ids, "reviewer-a")
    llm_reviewer = _write_submission(tmp_path / "llm_reviewer_submission.jsonl", pair_ids, "llm-reviewer", conflicts=True)

    import_research_review(reviewer_a, "reviewer_a", tmp_path / "review")
    status = import_research_review(llm_reviewer, "llm_reviewer", tmp_path / "review")
    assert status["conflicts"] == 1
    assert status["READY_FOR_SILVER"] is False

    try:
        promote_research_gold(manifest, tmp_path / "review", tmp_path / "gold")
    except ValueError as exc:
        assert "not ready" in str(exc)
    else:
        raise AssertionError("gold promotion should still require two human reviews")

    conflicts = build_llm_adjudication_queue(tmp_path / "review")
    assert len(conflicts) == 1
    adjudication = {
        "pair_id": conflicts[0]["pair_id"],
        "adjudicator_id": "human-adjudicator",
        "final_label": "supported",
        "final_study_design": "observational",
        "final_outcome": "mortality",
        "final_intervention_type": "biomarker-only",
        "final_evidence_strength": "low",
        "final_correlation_vs_causation": "correlational",
        "final_protocol_vs_results": "results",
        "final_evidence_quote_verified": "yes",
        "adjudication_notes": "resolved human/LLM disagreement",
        "adjudicated_at": "2026-08-31T00:00:00Z",
    }
    (tmp_path / "llm_adjudication.jsonl").write_text(json.dumps(adjudication) + "\n", encoding="utf-8")
    assert validate_llm_adjudication_submission(tmp_path / "llm_adjudication.jsonl", tmp_path / "review") == []
    status = adjudicate_llm_review(tmp_path / "llm_adjudication.jsonl", tmp_path / "review")
    assert status["READY_FOR_SILVER"] is True
    assert llm_review_status(tmp_path / "review")["READY_FOR_SILVER"] is True

    report = promote_research_silver(manifest, tmp_path / "review", tmp_path / "silver", dataset_id="fixture-silver")
    assert report["dataset_status"] == "silver"
    silver_manifest = load_json(tmp_path / "silver" / "research_dataset_manifest.json")
    assert silver_manifest["dataset_status"] == "silver"
    silver_pairs = load_jsonl(tmp_path / "silver" / "claim_evidence.jsonl")
    assert all(pair["review"]["annotator_b"]["annotator_id"] == "llm-reviewer" for pair in silver_pairs)
    assert validate_research_dataset(tmp_path / "silver" / "research_dataset_manifest.json") == []
