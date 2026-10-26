#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-}:$ROOT/src"
python -m pytest -q
python -m petlongevity_bench.cli validate --data data/demo/m1_gold.jsonl --schema schemas/evidence_schema.json
python -m petlongevity_bench.cli validate-dataset --manifest data/demo/dataset_m2_manifest.json
python -m petlongevity_bench.cli agreement-m2 --data data/demo/dataset_m2_records.jsonl >/dev/null
python -m petlongevity_bench.cli validate-research-dataset --manifest data/demo/research_dataset_synthetic_manifest.json >/dev/null
python scripts/run_demo_research_review_e2e.py >/dev/null
python -m petlongevity_bench.cli score-m1 --gold data/demo/m1_gold.jsonl --pred data/demo/m1_pred_perfect.jsonl >/dev/null
python -m petlongevity_bench.cli score-m2 --gold data/demo/m2_gold.jsonl --pred data/demo/m2_pred_perfect.jsonl >/dev/null
python -m petlongevity_bench.cli score-m3 --gold data/demo/m3_gold.jsonl --pred data/demo/m3_pred.jsonl >/dev/null
python -m petlongevity_bench.cli score-m4 --gold data/demo/m4_gold.jsonl --pred data/demo/m4_pred.jsonl >/dev/null
python -m petlongevity_bench.cli audit-leakage --sources data/demo/sources.jsonl --cutoff 2016-12-31 >/dev/null
TEMP_MANIFEST="$(mktemp "${TMPDIR:-/tmp}/petbench_snapshot.XXXXXX.json")"
TEMP_PREDICTIONS="$(mktemp "${TMPDIR:-/tmp}/petbench_predictions.XXXXXX.jsonl")"
TEMP_RUN_MANIFEST="$(mktemp "${TMPDIR:-/tmp}/petbench_run_manifest.XXXXXX.json")"
TEMP_RESPONSE_CACHE="$(mktemp "${TMPDIR:-/tmp}/petbench_response_cache.XXXXXX.jsonl")"
TEMP_B3_TRACE="$(mktemp "${TMPDIR:-/tmp}/petbench_b3_trace.XXXXXX.jsonl")"
TEMP_RESEARCH_CSV="$(mktemp "${TMPDIR:-/tmp}/petbench_research.XXXXXX.csv")"
trap 'rm -f "$TEMP_MANIFEST" "$TEMP_PREDICTIONS" "$TEMP_RUN_MANIFEST" "$TEMP_RESPONSE_CACHE" "$TEMP_B3_TRACE" "$TEMP_RESEARCH_CSV"' EXIT
python -m petlongevity_bench.cli convert-dataset --input data/demo/research_claim_evidence_synthetic.jsonl --output "$TEMP_RESEARCH_CSV" --from-format jsonl --to-format csv >/dev/null
python -m petlongevity_bench.cli freeze-snapshot --records data/demo/temporal_clean_sources.jsonl --output "$TEMP_MANIFEST" --snapshot-id smoke-temporal --source synthetic-qa --query 'synthetic pre-cutoff QA corpus' --cutoff 2016-12-31 --version-registry data/demo/temporal_version_registry.json --retrieved-at 2017-01-01 >/dev/null
python -m petlongevity_bench.cli audit-snapshot --manifest data/demo/temporal_clean_manifest.json >/dev/null
python -m petlongevity_bench.cli run-offline --module M1 --baseline B1 --inputs data/demo/m1_gold.jsonl --responses data/demo/m1_pred_perfect.jsonl --predictions "$TEMP_PREDICTIONS" --manifest "$TEMP_RUN_MANIFEST" --response-cache "$TEMP_RESPONSE_CACHE" --prompt prompts/M1_evidence_extraction.md --snapshot-manifest data/demo/temporal_clean_manifest.json --run-date 2026-01-01 >/dev/null
python -m petlongevity_bench.cli query-kg --nodes data/demo/kg_nodes.jsonl --edges data/demo/kg_edges.jsonl --node-id I:demo --species cat --direct-species-evidence --cutoff 2016-12-31 >/dev/null
python -m petlongevity_bench.cli run-b3-offline --module M2 --inputs data/demo/m2_gold.jsonl --responses data/demo/b3_m2_responses.jsonl --predictions "$TEMP_PREDICTIONS" --manifest "$TEMP_RUN_MANIFEST" --trace "$TEMP_B3_TRACE" --prompt prompts/M2_evidence_judgment.md --snapshot-manifest data/demo/temporal_clean_manifest.json --kg-nodes data/demo/kg_nodes.jsonl --kg-edges data/demo/kg_edges.jsonl --kg-node-id I:demo --species cat --run-date 2026-01-01 >/dev/null
echo "Codex verification passed."
