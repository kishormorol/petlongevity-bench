#!/usr/bin/env python3
"""Validate a downloaded full-paper clinician draft annotation submission."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.fulltext import validate_fulltext_draft_submission


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--submission", required=True)
parser.add_argument("--receipts", default="review/fulltext/fulltext_receipts.jsonl")
parser.add_argument("--base-dir", default="review/fulltext")
args = parser.parse_args()
try:
    errors = validate_fulltext_draft_submission(args.submission, args.receipts, args.base_dir)
except ValueError as exc:
    parser.error(str(exc))
print(json.dumps({"valid": not errors, "n_errors": len(errors), "errors": errors}, indent=2, sort_keys=True))
raise SystemExit(0 if not errors else 1)
