#!/usr/bin/env python3
"""Acquire the rights-aware, unannotated PubMed corpus."""
import argparse, json
from petlongevity_bench.corpus import acquire_corpus

p=argparse.ArgumentParser(); p.add_argument("--output",default="data/corpus"); p.add_argument("--email"); p.add_argument("--cutoff")
args=p.parse_args(); print(json.dumps(acquire_corpus(args.output,args.email,args.cutoff),indent=2,sort_keys=True))
