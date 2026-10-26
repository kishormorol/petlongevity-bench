#!/usr/bin/env python3
"""Build the abstract-review adjudication packet for current disagreements."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import build_research_adjudication_queue


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--review-dir", default="review/abstracts_300")
args = parser.parse_args()
print(json.dumps({"conflicts": len(build_research_adjudication_queue(args.review_dir))}, indent=2, sort_keys=True))
