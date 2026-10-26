#!/usr/bin/env python3
"""Run the synthetic research-review lifecycle fixture end to end."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from petlongevity_bench.datasets import validate_research_dataset
from petlongevity_bench.research_review import (
    adjudicate_llm_review,
    adjudicate_research_review,
    build_llm_adjudication_queue,
    build_research_adjudication_queue,
    export_m2_baseline_splits,
    import_research_review,
    promote_research_silver,
    prepare_research_review,
    promote_research_gold,
    validate_llm_adjudication_submission,
    validate_research_adjudication_submission,
    validate_research_review_submission,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "demo" / "research_review_e2e"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="petbench-review-e2e-") as tmp:
        work = Path(tmp)
        draft = work / "draft"
        submissions = work / "submissions"
        shutil.copytree(FIXTURE / "draft", draft)
        shutil.copytree(FIXTURE / "submissions", submissions)
        shutil.copy2(FIXTURE / "corpus_registry.jsonl", work / "corpus_registry.jsonl")

        manifest = draft / "research_dataset_manifest.json"
        review_dir = work / "review"
        gold_dir = work / "gold"
        silver_dir = work / "silver"
        m2_dir = work / "m2"
        assert not validate_research_dataset(manifest)
        prepare_research_review(manifest, review_dir, work / "corpus_registry.jsonl", "synthetic-review-e2e")

        reviewer_a = submissions / "reviewer_a.jsonl"
        reviewer_b = submissions / "reviewer_b.jsonl"
        llm_reviewer = submissions / "llm_reviewer.jsonl"
        adjudications = submissions / "adjudications.jsonl"
        llm_adjudications = submissions / "llm_adjudications.jsonl"
        assert not validate_research_review_submission(reviewer_a, review_dir)
        assert not validate_research_review_submission(reviewer_b, review_dir)
        assert not validate_research_review_submission(llm_reviewer, review_dir)
        import_research_review(reviewer_a, "reviewer_a", review_dir)
        llm_status = import_research_review(llm_reviewer, "llm_reviewer", review_dir)
        assert llm_status["conflicts"] == 1 and not llm_status["READY_FOR_SILVER"]
        llm_conflicts = build_llm_adjudication_queue(review_dir)
        assert len(llm_conflicts) == 1 and llm_conflicts[0]["pair_id"] == "SYNTH-RR-2"
        assert not validate_llm_adjudication_submission(llm_adjudications, review_dir)
        llm_status = adjudicate_llm_review(llm_adjudications, review_dir)
        assert llm_status["READY_FOR_SILVER"]
        silver = promote_research_silver(manifest, review_dir, silver_dir, "synthetic-research-review-e2e-silver")
        assert silver["pairs"] == 3
        assert not validate_research_dataset(silver_dir / "research_dataset_manifest.json")

        status = import_research_review(reviewer_b, "reviewer_b", review_dir)
        assert status["conflicts"] == 1 and not status["READY_TO_FREEZE"]

        conflicts = build_research_adjudication_queue(review_dir)
        assert len(conflicts) == 1 and conflicts[0]["pair_id"] == "SYNTH-RR-2"
        assert not validate_research_adjudication_submission(adjudications, review_dir)
        status = adjudicate_research_review(adjudications, review_dir)
        assert status["READY_TO_FREEZE"]

        promoted = promote_research_gold(manifest, review_dir, gold_dir, "synthetic-research-review-e2e-gold")
        assert promoted["pairs"] == 3
        assert not validate_research_dataset(gold_dir / "research_dataset_manifest.json")
        split_report = export_m2_baseline_splits(gold_dir / "claim_evidence.jsonl", review_dir / "splits.json", m2_dir)
        assert sum(split_report["splits"].values()) == 3
        print(json.dumps({"valid": True, "silver_pairs": silver["pairs"], "gold_pairs": promoted["pairs"], "m2_splits": split_report["splits"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
