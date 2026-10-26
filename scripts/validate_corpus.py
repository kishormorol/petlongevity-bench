#!/usr/bin/env python3
"""Validate registry and source integrity for the acquired corpus."""
import argparse, json
from petlongevity_bench.corpus import validate_corpus

p=argparse.ArgumentParser(); p.add_argument("--corpus",default="data/corpus")
args=p.parse_args(); errors=validate_corpus(args.corpus); print(json.dumps({"valid":not errors,"n_errors":len(errors),"errors":errors},indent=2,sort_keys=True)); raise SystemExit(1 if errors else 0)
