#!/usr/bin/env python3
import argparse, json
from petlongevity_bench.review import import_review
p=argparse.ArgumentParser(); p.add_argument("--decisions",required=True); p.add_argument("--reviewer-slot",choices=["reviewer_1","reviewer_2"],required=True); p.add_argument("--annotations",default="data/gold/v0_1/annotations.jsonl"); p.add_argument("--review-dir",default="review")
a=p.parse_args(); print(json.dumps(import_review(a.decisions,a.reviewer_slot,a.annotations,a.review_dir),indent=2,sort_keys=True))
