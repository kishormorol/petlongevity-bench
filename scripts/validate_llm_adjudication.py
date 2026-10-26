#!/usr/bin/env python3
"""Validate human/LLM adjudication submissions."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import validate_llm_adjudication_submission


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--submission", required=True)
parser.add_argument("--review-dir", default="review/abstracts_300")
parser.add_argument("--human-slot", choices=["reviewer_a", "reviewer_b"], default="reviewer_a")
args = parser.parse_args()
errors = validate_llm_adjudication_submission(args.submission, args.review_dir, args.human_slot)
print(json.dumps({"valid": not errors, "n_errors": len(errors), "errors": errors}, indent=2, sort_keys=True))
