# Synthetic Research Review E2E Fixture

This directory demonstrates the abstract-review lifecycle with synthetic data only. It is not a
scientific benchmark release and must not be copied into `data/gold/`.

The fixture includes:

- `draft/` - draft research manifest, synthetic paper registry, and claim/evidence pairs.
- `corpus_registry.jsonl` - minimal target-category/full-text status metadata for dashboards.
- `submissions/reviewer_a.jsonl` and `submissions/reviewer_b.jsonl` - complete reviewer files.
- `submissions/adjudications.jsonl` - one adjudicator decision for the intentional disagreement.
- `submissions/llm_reviewer.jsonl` - complete LLM reviewer file for the silver lane.
- `submissions/llm_adjudications.jsonl` - one adjudicator decision for the human/LLM disagreement.

Run `python scripts/run_demo_research_review_e2e.py` to copy these files into a temporary
workspace, prepare review packets, import reviewers, adjudicate conflicts, promote synthetic
silver and gold datasets, validate them, and export M2 split files.
