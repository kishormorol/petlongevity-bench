#!/usr/bin/env python3
"""Build chunked prompt packets for the llm_reviewer abstract-review slot."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.llm_review import build_llm_review_prompts


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--review-dir", default="review/abstracts_300")
parser.add_argument("--output-dir", default="review/abstracts_300/llm_prompts")
parser.add_argument("--max-pairs-per-prompt", type=int, default=20)
parser.add_argument("--reviewer-id", default="llm-reviewer")
args = parser.parse_args()
report = build_llm_review_prompts(args.review_dir, args.output_dir, args.max_pairs_per_prompt, args.reviewer_id)
print(json.dumps(report, indent=2, sort_keys=True))
