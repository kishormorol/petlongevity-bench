#!/usr/bin/env python3
"""Validate an abstract reviewer JSONL submission before import."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import validate_research_review_submission


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--submission", required=True)
parser.add_argument("--review-dir", default="review/abstracts_300")
args = parser.parse_args()
errors = validate_research_review_submission(args.submission, args.review_dir)
print(json.dumps({"valid": not errors, "n_errors": len(errors), "errors": errors}, indent=2, sort_keys=True))
raise SystemExit(1 if errors else 0)
