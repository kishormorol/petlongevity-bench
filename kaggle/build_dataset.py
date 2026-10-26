#!/usr/bin/env python3
"""Assemble the Kaggle dataset folder from a release bundle.

    python scripts/export_release.py \
        --annotations data/gold/drafts/abstracts_300/claim_evidence.jsonl --output release/
    python kaggle/build_dataset.py --release release/ --output kaggle_upload/
    kaggle datasets version -p kaggle_upload/ -m "<message>"

The release bundle is already licence-filtered; this only renames the pairs
file, adds flat CSV copies for Kaggle's previewer, and attaches the card and
metadata kept in kaggle/dataset/. The card text is the dataset description.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent / "dataset"

PAIR_COLUMNS = [
    "pair_id", "paper_id", "claim_id", "text_withheld", "claim_text", "span_start_char", "span_end_char",
    "species", "study_design", "intervention_type", "outcome", "correlation_vs_causation",
    "protocol_vs_results", "evidence_strength", "label", "review_status", "publication_date",
    "provenance_url", "source_text_sha256",
]
REGISTRY_COLUMNS = [
    "paper_id", "pmid", "doi", "pmcid", "title", "journal", "publication_date", "publication_year", "species",
    "target_species", "target_category", "intervention_category", "study_type_reported", "license",
    "licence_family", "open_access_status", "text_included", "abstract_chars", "abstract_sha256",
    "pubmed_url", "abstract",
]


def flat(value: object) -> object:
    """The corpus registry stores JSON-encoded strings; decode them for CSV."""
    if isinstance(value, str) and value[:1] in '"[{':
        try:
            value = json.loads(value)
        except ValueError:
            return value
    if isinstance(value, list):
        return ";".join(map(str, value))
    if value in ("null", None):
        return ""
    return value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default="release")
    ap.add_argument("--output", default="kaggle_upload")
    args = ap.parse_args()
    release, out = Path(args.release), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    pairs = [json.loads(line) for line in (release / "annotations.jsonl").open(encoding="utf-8")]
    with (out / "claim_evidence_pairs.jsonl").open("w", encoding="utf-8") as fh:
        for p in pairs:
            p["text_withheld"] = bool(p.pop("evidence_quote_withheld", False))
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    with (out / "claim_evidence_pairs.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, PAIR_COLUMNS)
        writer.writeheader()
        for p in pairs:
            span = p.get("supporting_span") or {}
            writer.writerow({
                **{k: flat(p.get(k)) for k in PAIR_COLUMNS if k in p},
                "span_start_char": span.get("start_char"),
                "span_end_char": span.get("end_char"),
                "review_status": (p.get("review") or {}).get("status"),
            })

    shutil.copy(release / "registry.jsonl", out / "registry.jsonl")
    with (out / "registry.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, REGISTRY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for line in (release / "registry.jsonl").open(encoding="utf-8"):
            row = json.loads(line)
            writer.writerow({k: flat(row.get(k)) for k in REGISTRY_COLUMNS})

    shutil.copy(release / "manifest.json", out / "manifest.json")
    shutil.copy(HERE / "README.md", out / "README.md")
    meta = json.loads((HERE / "dataset-metadata.json").read_text(encoding="utf-8"))
    meta["description"] = (HERE / "README.md").read_text(encoding="utf-8")
    (out / "dataset-metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"{len(pairs)} pairs -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
