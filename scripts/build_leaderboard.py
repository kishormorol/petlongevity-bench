#!/usr/bin/env python3
"""Build the static PetLongevity-Bench leaderboard portal."""
from __future__ import annotations
import argparse
import json
from petlongevity_bench.leaderboard import build_leaderboard
from petlongevity_bench.review_portal import build_fulltext_review_portal

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--submissions", default="leaderboard/submissions.jsonl")
parser.add_argument("--review-status", default="review/review_status.json")
parser.add_argument("--output", default="leaderboard/index.html")
args = parser.parse_args()
print(json.dumps(build_leaderboard(args.submissions, args.review_status, args.output), indent=2, sort_keys=True))
print(json.dumps(build_fulltext_review_portal("data/corpus/registry.jsonl", "review/fulltext/fulltext_receipts.jsonl", "review/fulltext", "leaderboard/review/index.html"), indent=2, sort_keys=True))
