#!/usr/bin/env python3
import argparse, json
from petlongevity_bench.review import prepare_review
p=argparse.ArgumentParser(); p.add_argument("--annotations",default="data/gold/v0_1/annotations.jsonl"); p.add_argument("--registry",default="data/corpus/registry.jsonl"); p.add_argument("--review-dir",default="review")
a=p.parse_args(); print(json.dumps(prepare_review(a.annotations,a.registry,a.review_dir),indent=2,sort_keys=True))
