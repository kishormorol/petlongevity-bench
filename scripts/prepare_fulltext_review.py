#!/usr/bin/env python3
"""Create a paper-level, rights-aware clinician review queue."""
import argparse
import json

from petlongevity_bench.fulltext import write_fulltext_queue


parser = argparse.ArgumentParser()
parser.add_argument("--registry", default="data/corpus/registry.jsonl")
parser.add_argument("--output-dir", default="review/fulltext")
args = parser.parse_args()
print(json.dumps(write_fulltext_queue(args.registry, args.output_dir), indent=2, sort_keys=True))
