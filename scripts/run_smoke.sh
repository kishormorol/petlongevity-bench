#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT"
python -m pytest -q
python -m petlongevity_bench.cli validate --data data/demo/m1_gold.jsonl --schema schemas/evidence_schema.json
python -m petlongevity_bench.cli score-m1 --gold data/demo/m1_gold.jsonl --pred data/demo/m1_pred_perfect.jsonl
python -m petlongevity_bench.cli score-m2 --gold data/demo/m2_gold.jsonl --pred data/demo/m2_pred_perfect.jsonl
python -m petlongevity_bench.cli score-m3 --gold data/demo/m3_gold.jsonl --pred data/demo/m3_pred.jsonl
python -m petlongevity_bench.cli score-m4 --gold data/demo/m4_gold.jsonl --pred data/demo/m4_pred.jsonl
python -m petlongevity_bench.cli audit-leakage --sources data/demo/sources.jsonl --cutoff 2016-12-31
