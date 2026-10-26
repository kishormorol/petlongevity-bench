#!/usr/bin/env python3
"""Build an adjudication queue for human/LLM abstract-review conflicts."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import build_llm_adjudication_queue


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--review-dir", default="review/abstracts_300")
parser.add_argument("--human-slot", choices=["reviewer_a", "reviewer_b"], default="reviewer_a")
args = parser.parse_args()
rows = build_llm_adjudication_queue(args.review_dir, args.human_slot)
print(json.dumps({"conflicts": len(rows), "human_slot": args.human_slot}, indent=2, sort_keys=True))
