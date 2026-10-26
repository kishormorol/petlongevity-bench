#!/usr/bin/env python3
"""Create the v0.1 machine-draft benchmark dataset from preserved PubMed abstracts only."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from petlongevity_bench.annotations_v01 import summary, write_csv, write_queue
from petlongevity_bench.io import load_jsonl, write_jsonl, write_json


def sentences(text: str) -> list[str]:
    raw=[s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) >= 20]
    terms=("result", "conclusion", "significant", "increased", "decreased", "improved", "reduced", "longer", "shorter", "associated", "correlat", "demonstrat", "found", "showed", "did not", "no ")
    ranked=sorted(enumerate(raw),key=lambda item:(sum(t in item[1].lower() for t in terms),item[0]),reverse=True)
    return [text for _,text in sorted(ranked[:3])]


def fields(row: dict[str, object], species: str) -> dict[str, object]:
    category=str(row["target_category"]); pmid=str(row["pmid"]); title=str(row["title"])
    base={"study_design":"observational","intervention":None,"intervention_type":"biomarker-only","comparator":None,"population":f"{species} population described in the PubMed abstract","sample_size":None,"outcome":"biomarker","endpoint_type":"biomarker","evidence_strength":"low","causal_status":"association_only","protocol_vs_result":"completed_result"}
    if pmid == "11991408": base.update(study_design="controlled trial",intervention="25% food restriction",intervention_type="diet",comparator="paired control dog",population="48 Labrador Retrievers",sample_size=48,outcome="lifespan",endpoint_type="hard",evidence_strength="moderate",causal_status="causal_supported")
    elif category=="dog_longevity_aging": base.update(outcome="lifespan",endpoint_type="hard")
    elif category=="dog_pharmacology": base.update(study_design="RCT",intervention=title.split(".")[0],intervention_type="drug",comparator="placebo or control as reported",outcome="mobility" if "osteoarthritis" in title.lower() else "cognition",endpoint_type="clinical",evidence_strength="moderate",causal_status="causal_supported")
    elif category=="dog_nutrition_cognition": base.update(study_design="controlled trial",intervention="dietary intervention",intervention_type="diet",comparator="control diet or group as reported",outcome="cognition",endpoint_type="clinical",evidence_strength="moderate",causal_status="causal_supported")
    elif category=="cat_aging_biomarkers": base.update(outcome="mortality" if pmid=="29393723" else "renal" if pmid=="24217707" else "biomarker",endpoint_type="clinical" if pmid=="24217707" else "biomarker")
    elif category=="cat_nutrition_aging": base.update(study_design="controlled trial",intervention="dietary intervention",intervention_type="diet",comparator="diet or age group as reported",outcome="renal" if pmid=="38084870" else "metabolic",endpoint_type="safety" if pmid=="38084870" else "surrogate",evidence_strength="moderate",causal_status="causal_supported")
    elif category=="falsification_or_null": base.update(study_design="controlled trial",intervention="vitamin E supplementation",intervention_type="nutrient",comparator="commercial renal diet without added vitamin E",outcome="mortality",endpoint_type="hard",evidence_strength="moderate",causal_status="causal_supported")
    return base


def transfer(index: int, source_species: str) -> tuple[str, str]:
    if index < 3 and source_species=="dog": return "dog_to_cat", "cats"
    if index < 6 and source_species=="cat": return "cat_to_dog", "dogs"
    if index < 9 and source_species=="dog": return "mouse_to_dog", "dogs"
    return "none", "cats" if source_species=="cat" else "dogs"


def annotation_species(row: dict[str, object]) -> str:
    """Use dog for the one explicitly mixed-species digestibility paper to retain both strata."""
    if str(row["pmid"]) == "34359256":
        return "dog"
    return "cat" if str(row["target_category"]).startswith("cat") or row["target_category"]=="falsification_or_null" else "dog"


def contradiction(quote: str) -> str:
    """Make a useful adversarial opposite without asserting facts beyond the abstract."""
    no_effect=("no ", "did not", "not significant", "no evidence", "no effect")
    if any(term in quote.lower() for term in no_effect):
        return "The study reported a positive effect on the measured endpoint."
    return "The study reported no effect on the measured endpoint."


def record(row: dict[str, object], number: int, quote: str, label: str, claim: str, extra: dict[str, object]) -> dict[str, object]:
    abstract=str(row["abstract"]); start=abstract.index(quote); source_species=annotation_species(row)
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    return {"annotation_id":f"V01-{row['pmid']}-{number}","paper_id":row["paper_id"],"pmid":row["pmid"],"doi":row["doi"],"species":source_species,"breed":row.get("breed"),"publication_date":row["publication_date"],**fields(row,source_species),"claim_text":claim,"gold_label":label,"species_transfer":"none","evidence_quote":quote,"evidence_section":"abstract","source_locator":str(Path("data") / "corpus" / "abstracts" / f"{row['pmid']}.txt"),"source_start_offset":start,"source_end_offset":start+len(quote),"annotator_id":"codex-gpt5-machine-draft","annotation_status":"draft","reviewer_id":None,"adjudication_notes":"Machine-created from a verbatim PubMed abstract; requires independent human review and adjudication.","confidence":0.55,"created_at":now,"updated_at":now,"generator_model":"Codex (GPT-5)","generator_prompt_version":"v0.3-A3-abstract-draft-1",**extra}


def create(corpus: Path, output: Path) -> list[dict[str, object]]:
    rows=load_jsonl(corpus / "registry.jsonl"); annotations=[]
    for index,row in enumerate(rows):
        quotes=sentences(str(row["abstract"]));
        if len(quotes)<3: raise ValueError(f"{row['paper_id']} has insufficient abstract evidence")
        # Three fixed strata yield 33 supported / 17 contradicted / 25 insufficient records.
        if index < 8:
            annotations += [record(row,1,quotes[0],"supported",quotes[0],{}), record(row,2,quotes[1],"supported",quotes[1],{}), record(row,3,quotes[2],"contradicted",contradiction(quotes[2]),{})]
        elif index < 17:
            annotations += [record(row,1,quotes[0],"supported",quotes[0],{}), record(row,2,quotes[1],"contradicted",contradiction(quotes[1]),{}), record(row,3,quotes[2],"insufficient",f"This paper establishes increased lifespan in all {('cats' if 'cat' in row['species'] else 'dogs')}.",{})]
        else:
            kind,target=transfer(index-17, annotation_species(row))
            extras={"species_transfer":kind} if kind!="none" else {}
            annotations += [record(row,1,quotes[0],"supported",quotes[0],{}), record(row,2,quotes[1],"insufficient",f"The reported finding establishes a therapeutic causal mechanism and lifespan benefit in {target}.",extras), record(row,3,quotes[2],"insufficient",f"The result establishes universal clinical disease treatment in {target}.",extras)]
    output.mkdir(parents=True,exist_ok=True); write_jsonl(output / "annotations.jsonl",annotations); write_csv(annotations,output / "annotations.csv"); write_json(output / "annotation_summary.json",summary(annotations)); write_queue(annotations,output / "adjudication_queue.csv")
    (output / "annotation_guidelines.md").write_text("# Annotation v0.1 review guidance\n\nAll records are machine-created drafts. Verify every quote and offset against the linked PubMed abstract, replace broad templates with paper-specific claims where warranted, and do not promote records to gold without independent human review/adjudication. A protocol cannot demonstrate efficacy; observational evidence cannot establish causality; species transfer, surrogate-to-lifespan, and safety-to-efficacy claims require explicit direct evidence.\n",encoding="utf-8")
    return annotations


if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--corpus",default="data/corpus"); parser.add_argument("--output",default="data/gold/v0_1")
    args=parser.parse_args(); print(json.dumps(summary(create(Path(args.corpus),Path(args.output))),indent=2,sort_keys=True))
