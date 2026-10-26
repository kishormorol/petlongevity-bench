#!/usr/bin/env python3
import argparse, json
from petlongevity_bench.review import build_adjudication_queue
p=argparse.ArgumentParser(); p.add_argument("--annotations",default="data/gold/v0_1/annotations.jsonl"); p.add_argument("--review-dir",default="review")
a=p.parse_args(); print(json.dumps({"conflicts":build_adjudication_queue(a.annotations,a.review_dir)},indent=2,sort_keys=True))
