#!/usr/bin/env python3
"""Import adjudicator decisions for human/LLM abstract-review conflicts."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import adjudicate_llm_review


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--submission", required=True)
parser.add_argument("--review-dir", default="review/abstracts_300")
parser.add_argument("--human-slot", choices=["reviewer_a", "reviewer_b"], default="reviewer_a")
args = parser.parse_args()
print(json.dumps(adjudicate_llm_review(args.submission, args.review_dir, args.human_slot), indent=2, sort_keys=True))
