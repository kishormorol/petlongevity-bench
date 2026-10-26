#!/usr/bin/env python3
"""Export claim/evidence pairs to M2 scoring files by paper-level split."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import export_m2_baseline_splits


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--claim-evidence", default="data/gold/v0_4/claim_evidence.jsonl")
parser.add_argument("--splits", default="review/abstracts_300/splits.json")
parser.add_argument("--output-dir", default="data/gold/v0_4/m2_splits")
args = parser.parse_args()
print(json.dumps(export_m2_baseline_splits(args.claim_evidence, args.splits, args.output_dir), indent=2, sort_keys=True))
