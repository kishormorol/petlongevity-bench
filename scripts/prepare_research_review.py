#!/usr/bin/env python3
"""Prepare abstract draft review packets, status, dashboard, and splits."""
from __future__ import annotations

import argparse
import json

from petlongevity_bench.research_review import prepare_research_review


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--manifest", default="data/gold/drafts/abstracts_300/research_dataset_manifest.json")
parser.add_argument("--output-dir", default="review/abstracts_300")
parser.add_argument("--corpus-registry", default="data/corpus/registry.jsonl")
parser.add_argument("--split-seed", default="petlongevity-v0.4-abstracts")
args = parser.parse_args()
print(
    json.dumps(
        prepare_research_review(args.manifest, args.output_dir, args.corpus_registry, args.split_seed),
        indent=2,
        sort_keys=True,
    )
)
