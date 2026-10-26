#!/usr/bin/env python3
"""Assemble validated LLM chunk responses into llm_reviewer JSONL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from petlongevity_bench.llm_review import assemble_llm_review_submission


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--review-dir", default="review/abstracts_300")
parser.add_argument("--responses-dir", default="review/abstracts_300/llm_prompts/responses")
parser.add_argument("--response", action="append", default=[])
parser.add_argument("--output", default="review/abstracts_300/llm_reviewer.jsonl")
parser.add_argument("--reviewer-id", default="llm-reviewer")
args = parser.parse_args()
response_paths = args.response or sorted(str(path) for path in Path(args.responses_dir).glob("*.jsonl"))
report = assemble_llm_review_submission(response_paths, args.review_dir, args.output, args.reviewer_id)
print(json.dumps(report, indent=2, sort_keys=True))
raise SystemExit(0 if report["valid"] else 1)
