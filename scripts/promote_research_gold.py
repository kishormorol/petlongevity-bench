#!/usr/bin/env python3
"""Promote fully reviewed abstract records to a gold research dataset."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import promote_research_gold


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--manifest", default="data/gold/drafts/abstracts_300/research_dataset_manifest.json")
parser.add_argument("--review-dir", default="review/abstracts_300")
parser.add_argument("--output-dir", default="data/gold/v0_4")
parser.add_argument("--dataset-id", default="petlongevity-abstract-gold-v0.4")
args = parser.parse_args()
try:
    report = promote_research_gold(args.manifest, args.review_dir, args.output_dir, args.dataset_id)
except ValueError as exc:
    print(json.dumps({"promoted": False, "error": str(exc)}, indent=2, sort_keys=True))
    raise SystemExit(1)
print(json.dumps(report, indent=2, sort_keys=True))
