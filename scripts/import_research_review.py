#!/usr/bin/env python3
"""Import one complete abstract reviewer submission into an append-only slot."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import import_research_review


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--submission", required=True)
parser.add_argument("--reviewer-slot", choices=["reviewer_a", "reviewer_b", "llm_reviewer"], required=True)
parser.add_argument("--review-dir", default="review/abstracts_300")
args = parser.parse_args()
print(json.dumps(import_research_review(args.submission, args.reviewer_slot, args.review_dir), indent=2, sort_keys=True))
