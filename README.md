# PetLongevity-Bench v0.2

Runnable, provider-neutral benchmark for evidence-grounded AI systems doing dog/cat healthy-aging research.

## What is implemented

- **M1 Evidence Extraction:** JSON-schema validation, field-level scoring, species/direction accuracy, span-overlap support, hallucinated-field rate.
- **M2 Evidence Judgment:** 3-way claim classification, species-transfer false positives, surrogate/protocol overclaiming, risk-weighted unsupported claims.
- **M3 Temporal Prioritization:** Recall@10/20/50, MRR, NDCG, calibration error. Unlabeled candidates should not be treated as true negatives in scientific reporting.
- **M4 Biomarker Forecasting:** ranking recall, direction agreement, cross-species concordance.
- **Leakage audit:** detects sources dated after a temporal cutoff.
- **PubMed snapshotter:** cutoff-filtered PubMed retrieval through NCBI E-utilities, producing JSONL + metadata.
- **Provider neutrality:** evaluate prediction JSONL from any LLM, agent framework, or local model.
- **Synthetic smoke-test fixtures:** clearly labeled demo data so the software can be tested without pretending synthetic records are scientific evidence.

## Data

This repository is the code. The corpus is third-party text, so it is not here:
`data/corpus/`, `data/gold/` and `review/` are referenced below but are not included.

- **Redistributable data** is on Kaggle: [kishormorol/petlongevity-bench](https://www.kaggle.com/datasets/kishormorol/petlongevity-bench) — the 100-paper registry, abstract text for the 34 CC BY papers, and 300 candidate claim/evidence pairs with offsets and hashes. See [DATA_LICENSE.md](DATA_LICENSE.md) and [kaggle/README.md](kaggle/README.md).
- **The full corpus** can be rebuilt from PubMed with `scripts/acquire_corpus.py` (see *Corpus* below); hashes in the Kaggle registry let you check you fetched the same text.
- **Benchmark task** on Kaggle Benchmarks: [petlongevity-bench-species-transfer](https://www.kaggle.com/benchmarks/tasks/kishormorol/petlongevity-bench-species-transfer).

The pair annotation fields in v0.2 are placeholders pending human review; do not score models against them.

## Install and run

```bash
python -m pip install -e .
petbench validate --data data/demo/m1_gold.jsonl --schema schemas/evidence_schema.json
petbench score-m1 --gold data/demo/m1_gold.jsonl --pred data/demo/m1_pred_perfect.jsonl
petbench score-m2 --gold data/demo/m2_gold.jsonl --pred data/demo/m2_pred_perfect.jsonl
petbench score-m3 --gold data/demo/m3_gold.jsonl --pred data/demo/m3_pred.jsonl
petbench score-m4 --gold data/demo/m4_gold.jsonl --pred data/demo/m4_pred.jsonl
petbench audit-leakage --sources data/demo/sources.jsonl --cutoff 2016-12-31
petbench validate-dataset --manifest data/demo/dataset_m2_manifest.json
petbench agreement-m2 --data data/demo/dataset_m2_records.jsonl
petbench validate-research-dataset --manifest data/demo/research_dataset_synthetic_manifest.json
petbench convert-dataset --input data/gold/claim_evidence.jsonl --output /tmp/claim_evidence.csv --from-format jsonl --to-format csv
petbench freeze-snapshot --records data/demo/temporal_clean_sources.jsonl --output /tmp/petbench_snapshot.json --snapshot-id demo --source synthetic-qa --query 'synthetic pre-cutoff QA corpus' --cutoff 2016-12-31 --version-registry data/demo/temporal_version_registry.json
petbench audit-snapshot --manifest /tmp/petbench_snapshot.json
petbench run-offline --module M1 --baseline B1 --inputs data/demo/m1_gold.jsonl --responses data/demo/m1_pred_perfect.jsonl --predictions /tmp/m1_predictions.jsonl --manifest /tmp/m1_run_manifest.json --response-cache /tmp/m1_responses.jsonl --prompt prompts/M1_evidence_extraction.md --snapshot-manifest data/demo/temporal_clean_manifest.json
petbench query-kg --nodes data/demo/kg_nodes.jsonl --edges data/demo/kg_edges.jsonl --node-id I:demo --species cat --direct-species-evidence --cutoff 2016-12-31
petbench run-b3-offline --module M2 --inputs data/demo/m2_gold.jsonl --responses data/demo/b3_m2_responses.jsonl --predictions /tmp/b3_predictions.jsonl --manifest /tmp/b3_run_manifest.json --trace /tmp/b3_trace.jsonl --prompt prompts/M2_evidence_judgment.md --snapshot-manifest data/demo/temporal_clean_manifest.json --kg-nodes data/demo/kg_nodes.jsonl --kg-edges data/demo/kg_edges.jsonl --kg-node-id I:demo --species cat
```

## Freeze a PubMed snapshot

```bash
export NCBI_API_KEY=...   # optional
petbench snapshot-pubmed \
  --query '(dog OR canine) AND (aging OR ageing OR longevity OR healthspan)' \
  --cutoff 2021-12-31 \
  --output data/pubmed_dog_2021.jsonl \
  --email you@example.com
```

The command stores the exact query, cutoff, retrieval date, and result count next to the snapshot. For temporal claims, also freeze non-PubMed databases and report model-pretraining contamination risk.

## Temporal firewall

Freeze an M3 corpus with `freeze-snapshot`; the manifest records its query, source,
retrieval date, cutoff, frozen-file and canonical-content SHA-256 hashes, record count,
and a version registry for every
database or knowledge graph. `audit-snapshot` is strict by default: a post-cutoff,
undated, unprovenanced, modified, or post-cutoff-version source produces a machine-readable
error report and a nonzero exit status. `--non-strict` permits undated/unprovenanced
sources for diagnostics only; post-cutoff sources still fail.

Run manifests must separately record `closed_model_pretraining_risk` as `unknown`,
`possible`, or `not_applicable`. A clean corpus cannot prove that a closed model lacked
post-cutoff pretraining knowledge. The prompt audit flags explicit ISO dates later than
the cutoff; it is a limited detector, not proof that a prompt is uncontaminated.

## B0/B1 model runner

`run-offline` is a credential-free reference runner for reproducible B0/B1 experiments.
It reads precomputed adapter responses, verifies that they exactly cover the requested
items and meet the moduleâ€™s prediction contract, then writes prediction JSONL, a hashed
raw-response cache, and a validated run manifest. B0 accepts no retrieval snapshot;
B1 requires a snapshot that passes the strict temporal audit. The manifest records model
identity/version, prompt and snapshot hashes, generation settings, raw-response hash, and
prediction hash. Generation settings and cached responses with secret-shaped fields are
rejected; API keys are never read or written by the core runner. Live-provider adapters
are deliberately outside the core package and must implement `ModelAdapter`.

## Species knowledge graph and B3 agent

The reference species KG uses typed JSONL nodes and edges. Evidence-bearing edges require
species, source ID/date, evidence level, and provenance URL. `query-kg` supports bounded
neighborhoods, direct-species filtering, and temporal cutoffs; direct feline queries never
use dog-only edges. No graph database is required.

`run-b3-offline` composes strict snapshot retrieval, a species-KG lookup, deterministic
tool traces, and claim verification. B3 response envelopes pair a schema-conforming
prediction with claims that either cite returned evidence IDs or are explicitly marked
`unsupported`/`uncertain`. Tool failures are saved in a sanitized trace and prevent claims
from being represented as supported. B3 writes the same M1â€“M4 prediction JSONL contracts
that the existing evaluator uses for B0â€“B3.

## Adjudicated M1/M2 datasets

Real-paper M1/M2 datasets use `schemas/dataset_manifest_schema.json` and
`schemas/annotation_adjudication_schema.json`. Each annotation carries a stable source
ID, publication date, provenance URL, two annotator identities, an adjudicator identity,
review status, and notes. `dataset_status: "gold"` requires `review.status:
"adjudicated"`; draft annotations remain valid only in a draft dataset. M2 records may
also contain the two categorical draft labels used by `agreement-m2` to report raw
agreement and Cohen's kappa. The dataset fixtures under `data/demo/` are explicitly
synthetic and are QA inputs, not scientific gold data.

## Research gold-data infrastructure

`data/gold/` is intentionally empty until qualified reviewers add real paper metadata
and annotations. A research manifest links a `paper_registry.jsonl` to
`claim_evidence.jsonl`; validate it with `petbench validate-research-dataset --manifest
data/gold/research_dataset_manifest.json`. Paper records require PMID and/or DOI, title,
publication year/date, species, and a provenance URL. Claim/evidence pairs require full
source provenance, a source-text SHA-256, exact character-offset supporting span, species,
study design, outcome, intervention type, evidence strength, M2 label,
correlation-vs-causation, protocol-vs-results, and paired-review/adjudication fields.

Allowed registry species are `dog`, `cat`, `mouse`, `human`, and `other`; study designs
are `RCT`, `controlled trial`, `cohort`, `observational`, `case study`, `in vitro`,
`review`, and `protocol`. JSONL/CSV round trips use `convert-dataset`. This repository
does not populate these files from model output or ship fabricated real-paper labels.

## Real scientific corpus acquisition

`data/corpus/` is a separate, unannotated 100-paper PubMed registry. Rebuild and validate it
without network access during normal tests using the checked-in artifacts; live acquisition is:

```bash
PYTHONPATH=src python scripts/acquire_corpus.py --output data/corpus --cutoff 2026-08-19
PYTHONPATH=src python scripts/validate_corpus.py --corpus data/corpus
```

Its manifest preserves the exact PubMed ID queries, candidate IDs, exclusions, retrieval date,
and temporal cutoff. Original PubMed XML is stored per paper in `data/corpus/metadata/`. Full
text is stored only when PMC OAI-PMH returns reusable article XML, or when a documented legacy
PMC OA package is already available; these files are kept in `data/corpus/sources/pmc/` with a
checksum and access/license record. All other papers remain metadata/abstract only. The corpus
has no claim or gold labels and must not be annotated from model output automatically.

As of the 2026-09-01 corpus expansion, 61 of the 100 papers have rights-cleared PMC sources;
the corresponding extracted plain-text sources and validated access receipts are under
`review/fulltext/`. The remaining 39 papers are intentionally excluded from paper-level
annotation until a lawful source is recorded.

`data/gold/drafts/abstracts_300/` contains 300 unadjudicated, verbatim PubMed-abstract
claim/evidence drafts (three per corpus paper). Each record links to a separately stored source
text file under `data/corpus/abstracts/`, whose SHA-256 and character offsets are verified by
`validate-research-dataset`. These are review work items, not gold labels: their draft fields
must be independently checked and adjudicated by qualified humans before any evaluation use.

Create the abstract-review workspace, quality dashboard, and paper-level train/dev/test-candidate
splits with:

```bash
petbench prepare-research-review --manifest data/gold/drafts/abstracts_300/research_dataset_manifest.json --output-dir review/abstracts_300 --corpus-registry data/corpus/registry.jsonl --split-seed petlongevity-v0.4-abstracts
```

`review/abstracts_300/reviewer_packet_blinded.*` and `reviewer_abstracts.html` omit machine draft
labels. `coordinator_packet.*` keeps those draft labels separate for audit and triage. The current
split sizes are 60/20/20 papers, corresponding to 180/60/60 draft pairs.

When two qualified reviewers return downloaded JSONL files, validate and import them into
separate append-only slots. A third `llm_reviewer` slot is supported for the benchmark's
LLM-assisted `silver` lane; it does not satisfy the two-human `gold` gate.

```bash
petbench validate-research-review --submission reviewer_a.jsonl --review-dir review/abstracts_300
petbench import-research-review --submission reviewer_a.jsonl --reviewer-slot reviewer_a --review-dir review/abstracts_300
petbench import-research-review --submission reviewer_b.jsonl --reviewer-slot reviewer_b --review-dir review/abstracts_300
petbench build-research-adjudication-queue --review-dir review/abstracts_300
```

For the LLM-assisted benchmark lane, import the LLM decisions into `llm_reviewer`, adjudicate
human/LLM conflicts, and promote a `silver` dataset:

```bash
petbench build-llm-review-prompts --review-dir review/abstracts_300 --output-dir review/abstracts_300/llm_prompts --max-pairs-per-prompt 20
petbench assemble-llm-review-submission --review-dir review/abstracts_300 --responses-dir review/abstracts_300/llm_prompts/responses --output review/abstracts_300/llm_reviewer.jsonl
petbench import-research-review --submission llm_reviewer.jsonl --reviewer-slot llm_reviewer --review-dir review/abstracts_300
petbench build-llm-adjudication-queue --review-dir review/abstracts_300 --human-slot reviewer_a
petbench adjudicate-llm-review --submission llm_adjudications.jsonl --review-dir review/abstracts_300
petbench llm-review-status --review-dir review/abstracts_300
petbench promote-research-silver --manifest data/gold/drafts/abstracts_300/research_dataset_manifest.json --review-dir review/abstracts_300 --output-dir data/gold/v0_4_silver
```

If the adjudication queue is non-empty, import adjudicator decisions, then promote only after
`research-review-status` reports `READY_TO_FREEZE: true`:

```bash
petbench adjudicate-research-review --submission adjudications.jsonl --review-dir review/abstracts_300
petbench research-review-status --review-dir review/abstracts_300
petbench promote-research-gold --manifest data/gold/drafts/abstracts_300/research_dataset_manifest.json --review-dir review/abstracts_300 --output-dir data/gold/v0_4
```

Promotion writes a schema-valid gold or silver research manifest plus baseline-ready M2 split
files under the selected output directory. This repository intentionally does not generate human
reviewer or adjudicator decisions automatically.

Reviewer/adjudicator file formats and the promotion command sequence are documented in
`docs/REVIEW_WORKFLOW.md`; the release checklist is in `docs/RELEASE_CHECKLIST_V0_4.md`.
The synthetic lifecycle fixture under `data/demo/research_review_e2e/` can be exercised with
`python scripts/run_demo_research_review_e2e.py`.

### Full-paper evidence review

Abstract drafts are triage material only and must never be finalized as paper-level gold
annotations. Create a clinician-facing inventory of the real papers with:

```bash
petbench prepare-fulltext-review --registry data/corpus/registry.jsonl --output-dir review/fulltext
```

The queue separates locally rights-cleared text, PMC records whose current access must be
confirmed, and papers requiring a lawfully obtained source. After a qualified reviewer or
institution supplies a lawful plain-text source, record its access basis, license/permission,
path, and SHA-256 in `fulltext_receipts.jsonl`, then validate it:

```bash
petbench validate-fulltext-receipts --receipts review/fulltext/fulltext_receipts.jsonl --registry data/corpus/registry.jsonl --base-dir review/fulltext
```

Only validated, full-paper sources may be used to create final claim/evidence pairs. Those
pairs still require two independent reviews and adjudication before the research dataset can
be marked gold.

When `data/corpus/` contains verified PMC full-text sources, create checksum-bound plain-text sources
and receipts without generating any claims or labels:

```bash
petbench extract-pmc-fulltext --registry data/corpus/registry.jsonl --corpus-dir data/corpus --output-dir review/fulltext
```

Create the clinician's draft worksheet only after the source receipts validate:

```bash
petbench prepare-fulltext-worksheet --registry data/corpus/registry.jsonl --receipts review/fulltext/fulltext_receipts.jsonl --base-dir review/fulltext --output-dir review/fulltext
```

### GitHub Pages clinician portal

Build the static clinician portal with the validated source texts embedded locally in the page:

```bash
PYTHONPATH=src python scripts/build_fulltext_review_portal.py
```

The deployed page is available under the leaderboard's `/review/` route. It lets a reviewer
select an exact passage in a clean article-body source (headings, paragraphs, and tables; no
journal metadata, affiliations, or reference list), records its character offsets, saves drafts only in that
browser, and downloads a JSONL submission for the coordinator. It does not upload annotations,
grant repository access, or create gold labels. The coordinator must validate the JSONL against
the source, import it into a separate reviewer slot, obtain an independent second review, and
adjudicate disagreements.

A 48-second silent practice walkthrough is linked at the top of the portal. Rebuild its committed
MP4 artifact with `PYTHONPATH=src python scripts/build_annotation_walkthrough_video.py`. It shows
the workflow only and does not contain a scientific annotation or gold label.

Validate a downloaded submission before any coordinator review or import:

```bash
PYTHONPATH=src python scripts/validate_fulltext_draft_submission.py --submission /path/to/clinician_submission.jsonl
```

## Scientific Annotation Dataset v0.1

`data/gold/v0_1/` contains 75 machine-created **draft** benchmark examples from the earlier
25-paper corpus. `data/gold/drafts/abstracts_120/` is the expanded 40-paper, 120-example
draft set, and `data/gold/drafts/abstracts_300/` is the larger 100-paper, 300-example
draft set. Every evidence quote has a checksum-verifiable local abstract and character offsets.
The dataset includes supported, contradicted, and insufficient claim variants, but no record is
adjudicated or eligible as benchmark gold. Validate it with:

```bash
petbench validate-annotations-v01 --annotations data/gold/v0_1/annotations.jsonl --registry data/corpus/registry.jsonl
```

The release summary and adjudication queue identify all records requiring independent review.
Do not infer efficacy, lifespan benefit, causal mechanism, or cross-species applicability from
these draft labels without source review.

## Human review and adjudication

Create the independent-review workspace with:

```bash
PYTHONPATH=src python scripts/prepare_review.py
petbench review-status
```

`review/reviewer_packet.*` contains only the machine proposal and source context. Each qualified
reviewer submits an explicit, complete decision file through `scripts/import_review.py` using a
separate reviewer slot. `scripts/build_adjudication_queue.py` exposes only disagreements to the
adjudicator, and `scripts/adjudicate.py` appends final conflict resolutions without changing the
machine proposal or either reviewer submission. `review-status` reports `READY_TO_FREEZE=true`
only after two reviews per record, adjudicated conflicts, and verified final evidence quotes.

## Prediction contracts

### M1
One JSON object per gold `record_id`, conforming to `schemas/evidence_schema.json`.

### M2
```json
{"item_id":"...","label":"supported|contradicted|insufficient","direct_species_evidence":true,"surrogate_vs_hard_endpoint":"...","efficacy_vs_protocol":"..."}
```

### M3
```json
{"candidate_id":"...","score":0.73,"confidence":0.64}
```

### M4
```json
{"feature_id":"...","score":0.81,"direction":"increase|decrease|mixed","cross_species_concordant":true}
```

## Scientific safety boundary

This software ranks and evaluates research hypotheses. It does **not** output veterinary dosing instructions, prescribe compounds, or establish safety/efficacy. Advancement to wet-lab or animal studies requires qualified scientific/veterinary review and applicable oversight.

## Repository layout

- `src/petlongevity_bench/metrics.py` â€” M1â€“M4 metrics
- `src/petlongevity_bench/leakage.py` â€” temporal leakage audit
- `src/petlongevity_bench/pubmed.py` â€” NCBI PubMed snapshotting
- `schemas/evidence_schema.json` â€” paper-level evidence record
- `configs/tasks.yaml` â€” benchmark modules/baselines
- `data/gold_anchors.csv` â€” literature anchor registry from v0.1
- `data/demo/` â€” synthetic executable fixtures
- `tests/` â€” unit tests


## Build this repository with Codex

This copy is prepared for Codex. `AGENTS.md` contains durable repository rules, `PLANS.md` contains living execution plans, and `codex_prompts/` contains one focused prompt per v0.3 milestone.

Recommended first session:

```bash
git init
git add .
git commit -m "baseline PetLongevity-Bench v0.2"
codex
```

Then paste the contents of `codex_prompts/01_v03a_dataset_infrastructure.md`, or tell Codex: `Implement Milestone V0.3-A from PLANS.md and follow AGENTS.md.`

Verify after each milestone with:

```bash
bash scripts/codex_verify.sh
```

Use a separate Git branch/worktree for each milestone when running multiple agents in parallel. Do not parallelize milestones that depend on one another.

## Next scientific-data milestone

The code is runnable now. To become a publishable benchmark, v0.3 should add adjudicated annotations from real papers: ~100 M1 papers, ~150 M2 claim/evidence pairs, frozen drug/nutrition candidate universes for M3, and pre-cutoff omics variables + future labels for M4.

## Baseline prompts and manifests

`prompts/` contains stable prompt contracts for M1â€“M4. Hash these prompt files into each temporal run manifest. `schemas/run_manifest_schema.json` defines the reproducibility fields required for B0â€“B3 comparisons.

The repo intentionally does not hard-code a commercial LLM provider. A benchmark runner should write prediction JSONL matching the contracts above; the evaluator then scores every provider identically.

## Current build status

`reports/smoke_test_results.json` records the verified software smoke test. All five unit tests pass, M1/M2 perfect demo predictions score 1.0 on their principal accuracy metrics, and the leakage fixture correctly flags the 2017 source against a 2016-12-31 cutoff.

## Leaderboard portal

Build the standalone, provenance-first portal with:

```bash
PYTHONPATH=src python scripts/build_leaderboard.py
```

The resulting `leaderboard/index.html` ranks only verified, reproducible submissions from
`leaderboard/submissions.jsonl`. Pending submissions may be displayed for transparency but
are not ranked; synthetic demo scores are never benchmark results. See
`leaderboard/README.md` for the submission record contract.

The portal publishes automatically to GitHub Pages after a change to its source or review
status reaches `main`.
