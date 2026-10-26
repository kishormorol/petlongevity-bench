#!/usr/bin/env python3
"""Validate lawful full-text sources before paper-level annotation."""
import argparse
import json

from petlongevity_bench.fulltext import validate_fulltext_receipts


parser = argparse.ArgumentParser()
parser.add_argument("--receipts", required=True)
parser.add_argument("--registry", default="data/corpus/registry.jsonl")
parser.add_argument("--base-dir", required=True)
args = parser.parse_args()
errors = validate_fulltext_receipts(args.receipts, args.registry, args.base_dir)
print(json.dumps({"valid": not errors, "n_errors": len(errors), "errors": errors}, indent=2, sort_keys=True))
raise SystemExit(1 if errors else 0)
