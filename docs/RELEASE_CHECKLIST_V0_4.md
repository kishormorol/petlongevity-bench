# V0.4 Release Checklist

Use this checklist before publishing an adjudicated `v0.4` benchmark release.

## Review

- [ ] Assign two qualified independent reviewers.
- [ ] Send reviewers only `reviewer_abstracts.html` or `reviewer_packet_blinded.*`.
- [ ] Validate reviewer A submission.
- [ ] Import reviewer A into `reviewer_a`.
- [ ] Validate reviewer B submission.
- [ ] Import reviewer B into `reviewer_b`.
- [ ] Build the adjudication queue.
- [ ] Validate and import adjudication decisions for every conflict.
- [ ] Confirm `petbench research-review-status --review-dir review/abstracts_300` reports `READY_TO_FREEZE: true`.

## LLM-Assisted Silver

- [ ] Build LLM prompt chunks with `petbench build-llm-review-prompts --review-dir review/abstracts_300 --output-dir review/abstracts_300/llm_prompts`.
- [ ] Open an LLM reviewer tracking issue from `.github/ISSUE_TEMPLATE/llm-reviewer-submission.md`.
- [ ] Assemble LLM chunk responses with `petbench assemble-llm-review-submission --review-dir review/abstracts_300 --responses-dir review/abstracts_300/llm_prompts/responses --output review/abstracts_300/llm_reviewer.jsonl`.
- [ ] Import LLM decisions only into `llm_reviewer`.
- [ ] Build the LLM adjudication queue with `petbench build-llm-adjudication-queue --review-dir review/abstracts_300 --human-slot reviewer_a`.
- [ ] Validate and import human/LLM adjudication decisions for every conflict.
- [ ] Confirm `petbench llm-review-status --review-dir review/abstracts_300` reports `READY_FOR_SILVER: true`.
- [ ] Promote LLM-assisted labels only with `petbench promote-research-silver`.

## Promotion

- [ ] Run `petbench promote-research-gold --manifest data/gold/drafts/abstracts_300/research_dataset_manifest.json --review-dir review/abstracts_300 --output-dir data/gold/v0_4`.
- [ ] Run `petbench validate-research-dataset --manifest data/gold/v0_4/research_dataset_manifest.json`.
- [ ] Confirm `data/gold/v0_4/m2_splits/` was generated.
- [ ] Run baseline scoring only against adjudicated gold files.

## Validation

- [ ] Run `git diff --check`.
- [ ] Run `python -m pytest --basetemp .pytest_tmp`.
- [ ] Run `python scripts/validate_corpus.py --corpus data/corpus`.
- [ ] Run `petbench validate-fulltext-receipts --receipts review/fulltext/fulltext_receipts.jsonl --registry data/corpus/registry.jsonl --base-dir review/fulltext`.
- [ ] Run `python scripts/run_demo_research_review_e2e.py`.

## Publication

- [ ] Update leaderboard entries only from verified run manifests.
- [ ] Confirm demo fixtures are not presented as benchmark results.
- [ ] Tag the release after CI passes.
- [ ] Archive reviewer/adjudicator audit files according to project policy.
