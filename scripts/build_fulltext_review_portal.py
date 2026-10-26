#!/usr/bin/env python3
"""Build the static full-paper clinician review portal for GitHub Pages."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.review_portal import build_fulltext_review_portal


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--registry", default="data/corpus/registry.jsonl")
parser.add_argument("--receipts", default="review/fulltext/fulltext_receipts.jsonl")
parser.add_argument("--base-dir", default="review/fulltext")
parser.add_argument("--output", default="leaderboard/review/index.html")
args = parser.parse_args()
print(json.dumps(build_fulltext_review_portal(args.registry, args.receipts, args.base_dir, args.output), indent=2, sort_keys=True))
