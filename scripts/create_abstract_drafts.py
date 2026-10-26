#!/usr/bin/env python3
"""Create unadjudicated, verbatim-abstract draft claim/evidence pairs.

This script never creates gold labels.  It emits exactly three traceable draft excerpts per
registered paper, for qualified reviewers to replace or adjudicate.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from petlongevity_bench.io import load_jsonl, write_json, write_jsonl
from petlongevity_bench.io import sha256_file


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if len(sentence.strip()) >= 20]


def _evidence_sentences(text: str) -> list[str]:
    """Prefer reported findings/conclusions over background, aims, and sample counts."""
    findings=("result", "conclusion", "significant", "increased", "decreased", "improved", "reduced", "longer", "shorter", "associated", "correlat", "demonstrat", "found", "showed", "did not", "no ")
    sentences=_sentences(text)
    ranked=sorted(enumerate(sentences), key=lambda item: (sum(term in item[1].lower() for term in findings), item[0]), reverse=True)
    return [sentence for _,sentence in sorted(ranked[:3])]


def _fields(row: dict[str, object]) -> tuple[str, str, str, str, str]:
    category=str(row["target_category"])
    if category == "dog_pharmacology":
        return "RCT", "mobility" if "osteoarthritis" in str(row["title"]).lower() else "cognition", "drug", "causal", "results"
    if category == "dog_nutrition_cognition":
        return "controlled trial", "cognition", "diet", "causal", "results"
    if category == "cat_nutrition_aging":
        title=str(row["title"]).lower()
        return "controlled trial", "renal" if any(term in title for term in ("salt", "kidney", "renal")) else "metabolic", "diet", "causal", "results"
    if category == "cat_health_screening":
        return "observational", "biomarker", "biomarker-only", "correlational", "results"
    if category == "cat_cognitive_aging":
        return "observational", "cognition", "biomarker-only", "correlational", "results"
    if category == "cat_ckd_survival":
        title=str(row["title"]).lower()
        intervention="drug" if any(term in title for term in ("iodine", "methimazole", "radioiodine", "hyperthyroid")) else "biomarker-only"
        return "observational", "mortality", intervention, "correlational", "results"
    if category == "falsification_or_null":
        return "controlled trial", "mortality", "nutrient", "causal", "results"
    if category == "dog_biomarkers":
        return "observational", "biomarker", "biomarker-only", "correlational", "results"
    return "observational", "lifespan" if category == "dog_longevity_aging" else "biomarker", "biomarker-only", "correlational", "results"


def create(corpus: Path, output: Path) -> None:
    rows=load_jsonl(corpus / "registry.jsonl")
    source_dir=corpus / "abstracts"; source_dir.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    papers=[]; pairs=[]
    for row in rows:
        abstract=str(row.get("abstract") or "")
        sentences=_evidence_sentences(abstract)
        if len(sentences) < 3:
            raise ValueError(f"{row['paper_id']} has fewer than three usable abstract sentences")
        source=source_dir / f"{row['pmid']}.txt"; source.write_text(abstract, encoding="utf-8", newline="\n")
        digest=sha256_file(source)
        papers.append({key:row[key] for key in ("paper_id","pmid","doi","title","publication_year","publication_date","species") } | {"provenance_url":row["pubmed_url"]})
        study_design,outcome,intervention,causality,kind=_fields(row)
        for number, sentence in enumerate(sentences[:3], 1):
            start=abstract.index(sentence); end=start+len(sentence)
            pairs.append({
                "pair_id":f"{row['pmid']}-A{number}", "paper_id":row["paper_id"], "claim_id":f"{row['pmid']}-C{number}",
                "claim_text":sentence, "source_id":f"PMID:{row['pmid']}", "publication_date":row["publication_date"],
                "provenance_url":row["pubmed_url"], "source_text_sha256":digest,
                "source_text_path":(Path("..") / ".." / ".." / "corpus" / "abstracts" / source.name).as_posix(),
                "supporting_span":{"text":sentence,"start_char":start,"end_char":end}, "species":row["species"],
                "study_design":study_design, "outcome":outcome, "intervention_type":intervention,
                "evidence_strength":"low", "label":"supported", "correlation_vs_causation":causality,
                "protocol_vs_results":kind,
                "review":{"annotator_a":{"annotator_id":"automated-draft-extraction"},"annotator_b":{"annotator_id":"unassigned"},"adjudicator":{"annotator_id":"unassigned"},"status":"draft","notes":"Verbatim PubMed abstract excerpt; requires independent human annotation and adjudication."},
            })
    write_jsonl(output / "paper_registry.jsonl", papers)
    write_jsonl(output / "claim_evidence.jsonl", pairs)
    write_json(output / "research_dataset_manifest.json", {"dataset_id":f"petlongevity-abstract-drafts-{len(pairs)}","schema_version":"1.0","dataset_status":"draft","paper_registry_file":"paper_registry.jsonl","claim_evidence_file":"claim_evidence.jsonl","description":"Unadjudicated verbatim PubMed-abstract draft pairs for human scientific review; not gold labels.","license":"Metadata and abstracts retain their original source terms; annotation drafts are CC0."})


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--corpus", default="data/corpus"); parser.add_argument("--output", default="data/gold/drafts/abstracts_300")
    args=parser.parse_args(); create(Path(args.corpus), Path(args.output))
