# Abstract Review Workflow

This document describes the `abstracts_300` review workflow. These files are research annotation
work items, not clinical guidance and not benchmark gold until the promotion gate passes.

## Reviewer Submission

Reviewers use `review/abstracts_300/reviewer_abstracts.html` or
`reviewer_packet_blinded.jsonl`. The submitted JSONL must contain exactly one row per `pair_id`.
Build local ZIP handoff packets with:

```bash
python scripts/build_reviewer_handoff.py
```

The generated ZIP files are written under `review/abstracts_300/handoff/`, which is intentionally
git-ignored because it is a delivery artifact.

Required fields:

```json
{"pair_id":"123-A1","reviewer_id":"reviewer-a","label":"supported","study_design":"observational","outcome":"biomarker","intervention_type":"biomarker-only","evidence_strength":"low","correlation_vs_causation":"correlational","protocol_vs_results":"results","evidence_quote_verified":"yes","notes":"The quote directly states the abstract finding."}
```

Allowed labels: `supported`, `contradicted`, `insufficient`.

Allowed `evidence_quote_verified` values: `yes`, `no`. A final `no` blocks promotion.

Validate and import reviewer files:

```bash
petbench validate-research-review --submission reviewer_a.jsonl --review-dir review/abstracts_300
petbench import-research-review --submission reviewer_a.jsonl --reviewer-slot reviewer_a --review-dir review/abstracts_300
petbench import-research-review --submission reviewer_b.jsonl --reviewer-slot reviewer_b --review-dir review/abstracts_300
```

Reviewer slots are append-only. To replace a submission, make a new review workspace or preserve
the old file elsewhere with an explicit audit note.

## LLM Reviewer Slot

An LLM may be imported only into the explicit `llm_reviewer` slot. This lane can produce a
`silver` benchmark with one human reviewer plus one LLM reviewer; it does not satisfy the
two-human `gold` gate.

Build chunked LLM prompt packets from the same blinded reviewer packet:

```bash
petbench build-llm-review-prompts --review-dir review/abstracts_300 --output-dir review/abstracts_300/llm_prompts --max-pairs-per-prompt 20
```

The generated `llm_prompts/` directory is intentionally git-ignored. It contains
`instructions.md`, `response_schema.json`, a prompt manifest, and numbered chunk prompt files.
Save model JSONL responses under `review/abstracts_300/llm_prompts/responses/`, then assemble,
validate, and import:

```bash
petbench assemble-llm-review-submission --review-dir review/abstracts_300 --responses-dir review/abstracts_300/llm_prompts/responses --output review/abstracts_300/llm_reviewer.jsonl
petbench validate-research-review --submission llm_reviewer.jsonl --review-dir review/abstracts_300
petbench import-research-review --submission llm_reviewer.jsonl --reviewer-slot llm_reviewer --review-dir review/abstracts_300
petbench build-llm-adjudication-queue --review-dir review/abstracts_300 --human-slot reviewer_a
```

If the human and LLM disagree, validate and import adjudicator decisions:

```bash
petbench validate-llm-adjudication --submission llm_adjudications.jsonl --review-dir review/abstracts_300
petbench adjudicate-llm-review --submission llm_adjudications.jsonl --review-dir review/abstracts_300
```

## Adjudication

After both reviewer files are imported, build the conflict packet:

```bash
petbench build-research-adjudication-queue --review-dir review/abstracts_300
```

If conflicts exist, the adjudicator submission must cover exactly those `pair_id` values.

Required adjudicator fields:

```json
{"pair_id":"123-A1","adjudicator_id":"adjudicator-1","final_label":"supported","final_study_design":"observational","final_outcome":"biomarker","final_intervention_type":"biomarker-only","final_evidence_strength":"low","final_correlation_vs_causation":"correlational","final_protocol_vs_results":"results","final_evidence_quote_verified":"yes","adjudication_notes":"Reviewer B overread the endpoint; final label follows the quote.","adjudicated_at":"2026-08-30T00:00:00Z"}
```

Validate and import adjudication:

```bash
petbench validate-research-adjudication --submission adjudications.jsonl --review-dir review/abstracts_300
petbench adjudicate-research-review --submission adjudications.jsonl --review-dir review/abstracts_300
```

## Promotion

Promotion is blocked until every pair has two complete reviews, all disagreement fields are
adjudicated, and all final quotes are verified.

```bash
petbench research-review-status --review-dir review/abstracts_300
petbench promote-research-gold --manifest data/gold/drafts/abstracts_300/research_dataset_manifest.json --review-dir review/abstracts_300 --output-dir data/gold/v0_4
```

Promotion writes:

- `data/gold/v0_4/research_dataset_manifest.json`
- `data/gold/v0_4/paper_registry.jsonl`
- `data/gold/v0_4/claim_evidence.jsonl`
- `data/gold/v0_4/m2_splits/*_m2_gold.jsonl`

LLM-assisted promotion writes the same file shapes with `dataset_status: "silver"`:

```bash
petbench llm-review-status --review-dir review/abstracts_300
petbench promote-research-silver --manifest data/gold/drafts/abstracts_300/research_dataset_manifest.json --review-dir review/abstracts_300 --output-dir data/gold/v0_4_silver
```

Run the synthetic lifecycle fixture:

```bash
python scripts/run_demo_research_review_e2e.py
```
