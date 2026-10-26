#!/usr/bin/env python3
"""Promote one human plus one LLM abstract review to a silver benchmark dataset."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import promote_research_silver


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--manifest", default="data/gold/drafts/abstracts_300/research_dataset_manifest.json")
parser.add_argument("--review-dir", default="review/abstracts_300")
parser.add_argument("--output-dir", default="data/gold/v0_4_silver")
parser.add_argument("--dataset-id", default="petlongevity-abstract-silver-v0.4")
parser.add_argument("--human-slot", choices=["reviewer_a", "reviewer_b"], default="reviewer_a")
args = parser.parse_args()
report = promote_research_silver(args.manifest, args.review_dir, args.output_dir, args.dataset_id, args.human_slot)
print(json.dumps(report, indent=2, sort_keys=True))
