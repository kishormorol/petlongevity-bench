#!/usr/bin/env python3
"""Import adjudicator decisions for abstract-review disagreements."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import adjudicate_research_review


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--submission", required=True)
parser.add_argument("--review-dir", default="review/abstracts_300")
args = parser.parse_args()
print(json.dumps(adjudicate_research_review(args.submission, args.review_dir), indent=2, sort_keys=True))
