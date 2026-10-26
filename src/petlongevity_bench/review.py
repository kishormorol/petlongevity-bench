"""Append-only human review, disagreement, and adjudication workflow."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .io import load_jsonl, write_json, write_jsonl
from .annotations_v01 import validate_annotations

REVIEW_FIELDS = ("label_decision", "species_decision", "study_design_decision", "causal_status_decision", "protocol_vs_result_decision", "evidence_strength_decision", "evidence_quote_verified", "source_support_quality", "reviewer_confidence", "reviewer_notes", "review_timestamp")
_AGREEMENT_FIELDS = ("label_decision", "species_decision", "causal_status_decision", "protocol_vs_result_decision", "evidence_quote_verified", "study_design_decision")
_LABELS = {"supported", "contradicted", "insufficient"}
_SPECIES = {"dog", "cat", "mouse", "human", "other"}
_DESIGNS = {"RCT", "controlled trial", "cohort", "observational", "case study", "in vitro", "review", "protocol"}
_CAUSAL = {"causal_supported", "association_only", "causal_not_established", "not_applicable"}
_PROTOCOL = {"protocol", "completed_result", "not_applicable"}
_STRENGTH = {"high", "moderate", "low", "very_low"}


def _paths(review_dir: Path) -> dict[str, Path]:
    return {"r1":review_dir / "reviews" / "reviewer_1.jsonl", "r2":review_dir / "reviews" / "reviewer_2.jsonl", "adjudications":review_dir / "adjudications.jsonl", "conflicts":review_dir / "conflicts.csv", "packet":review_dir / "reviewer_packet.jsonl", "status":review_dir / "review_status.json"}


def _csv(rows: Iterable[dict[str, Any]], path: Path) -> None:
    rows=list(rows); path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,"w",encoding="utf-8",newline="") as handle:
        fields=list(rows[0]) if rows else ["annotation_id"]
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        for row in rows: writer.writerow({k:json.dumps(v,ensure_ascii=False) for k,v in row.items()})


def _load(path: Path) -> list[dict[str, Any]]:
    return load_jsonl(path) if path.exists() else []


def prepare_review(annotations_path: str | Path, registry_path: str | Path, review_dir: str | Path) -> dict[str, Any]:
    """Create reviewer packets containing proposals and source context, but no review decisions."""
    annotations=load_jsonl(annotations_path); papers={p["paper_id"]:p for p in load_jsonl(registry_path)}; root=Path(review_dir); root.mkdir(parents=True,exist_ok=True)
    packet=[]
    for item in annotations:
        paper=papers[item["paper_id"]]; source=Path(item["source_locator"]); text=source.read_text(encoding="utf-8") if source.exists() else ""
        start=item["source_start_offset"]; end=item["source_end_offset"]
        packet.append({"annotation_id":item["annotation_id"],"paper_id":item["paper_id"],"pmid":item["pmid"],"doi":item["doi"],"paper_title":paper["title"],"publication_year":paper["publication_year"],"species":item["species"],"machine_study_design":item["study_design"],"claim_text":item["claim_text"],"machine_gold_label":item["gold_label"],"machine_causal_status":item["causal_status"],"machine_protocol_vs_result":item["protocol_vs_result"],"machine_evidence_strength":item["evidence_strength"],"evidence_quote":item["evidence_quote"],"evidence_section":item["evidence_section"],"source_locator":item["source_locator"],"source_context":text[max(0,start-200):min(len(text),end+200)],"machine_confidence":item["confidence"]})
    write_jsonl(_paths(root)["packet"],packet); _csv(packet,root / "reviewer_packet.csv")
    (root / "reviewer_guidelines.md").write_text("""# Clinician reviewer guide\n\n## Purpose\n\nPetLongevity-Bench evaluates whether AI research systems accurately interpret dog and cat healthy-aging evidence. It is **not** a clinical guideline and does not ask you to recommend treatment, dosing, or patient care. Your review helps create a human-adjudicated reference set against which AI outputs can be assessed.\n\nEach item contains a proposed claim, an exact excerpt from a PubMed abstract, and nearby abstract context. Please judge only what the provided source establishes. The machine proposal is a fallible starting point, not an answer key.\n\n## How to review each item\n\n1. Read the claim.\n2. Confirm that the exact quoted text appears in the source context.\n3. Decide whether that source supports, contradicts, or is insufficient for the claim.\n4. Classify the study and evidence scope using the definitions below.\n5. Add a brief note, especially when the claim overreaches the evidence or the abstract leaves uncertainty.\n\nYou may work in multiple sessions. The local form saves completed items in that browser until you download the final JSONL file. Do not view the other reviewer's completed form or submission before you submit yours.\n\n## Core label\n\n- **Supported** — the quoted evidence directly justifies the claim at its stated scope.\n- **Contradicted** — the quoted evidence directly conflicts with the claim.\n- **Insufficient** — the source does not establish the claim. This includes claims that go beyond the species, endpoint, population, design, or certainty described.\n\n## Scope checks\n\n- **Species:** dog-only evidence is not direct evidence in cats, and cat-only evidence is not direct evidence in dogs.\n- **Causality:** an association or cross-sectional difference does not establish that an intervention caused an outcome.\n- **Endpoint:** a biomarker, laboratory value, cellular observation, or cognitive measure is not proof of lifespan, disease prevention, or broad clinical benefit unless the source explicitly demonstrates that endpoint.\n- **Study status:** a protocol describes a planned study; it is not a result.\n- **Evidence strength:** choose high only for especially direct, well-controlled evidence for the actual claim. Abstract-only evidence will often warrant moderate, low, or very low confidence in the claim's broader interpretation.\n\n## Form fields in plain language\n\n- **Study design:** use the closest description of the work actually reported.\n- **Causal conclusion:** choose *causal supported* only if the design and result support a causal conclusion for the stated outcome; otherwise choose *association only* or *causal not established*.\n- **Exact quote verified:** choose yes only when the displayed quote is present and accurate in the source context.\n- **Directness of support:** *direct* means the quote addresses the claim as stated; *partial* means it supports only part; *indirect* means it is relevant but requires an inference; *none* means it does not support the chosen label.\n- **Confidence:** use 0 to 1 to indicate confidence in your review decision, not confidence that an intervention works.\n\n## Submission and privacy\n\nOpen only your assigned `reviewer_1.html` or `reviewer_2.html`, complete all items, and select **Finish: validate & download**. Send the downloaded file to the study coordinator, who will import it into your assigned reviewer slot. Your response is stored separately and cannot be overwritten; disagreements are later reviewed through a documented adjudication process.\n""",encoding="utf-8")
    (root / "README.md").write_text("""# Review workspace\n\nStart with `reviewer_guidelines.md`, then open only your assigned `reviewer_1.html` or `reviewer_2.html` locally. The form presents one claim at a time, saves work in your browser, and downloads your completed decisions as a JSONL file. The work is research annotation only; it does not request clinical advice, treatment recommendations, or dosing.\n\nThe yellow machine proposal is a fallible draft, not an answer key. Do not inspect the other reviewer's submission before submitting yours. Send your downloaded file to the coordinator, who imports it through `scripts/import_review.py` into your separate, append-only reviewer slot. Any disagreement is retained and resolved later in a separate adjudication record; neither review is overwritten.\n\n`reviewer_packet.*` contains the source packet. Run `petbench review-status` to inspect readiness; it stays false until every item has two independent reviews, conflicts are adjudicated, quotes are verified, and source provenance passes validation.\n""",encoding="utf-8")
    _csv([],root / "adjudication_packet.csv"); _csv([],root / "conflicts.csv")
    return build_status(annotations,root)


def _validate_decision(item: dict[str, Any], slot: str, known: set[str]) -> None:
    if item.get("annotation_id") not in known: raise ValueError("review references unknown annotation_id")
    if item.get("reviewer_id") in {None,""}: raise ValueError("reviewer_id is required")
    if any(item.get(key) in {None,""} for key in REVIEW_FIELDS): raise ValueError("all reviewer decision fields require explicit input")
    checks={"label_decision":_LABELS,"species_decision":_SPECIES,"study_design_decision":_DESIGNS,"causal_status_decision":_CAUSAL,"protocol_vs_result_decision":_PROTOCOL,"evidence_strength_decision":_STRENGTH,"evidence_quote_verified":{"yes","no"},"source_support_quality":{"direct","partial","indirect","none"}}
    if any(item.get(key) not in choices for key,choices in checks.items()): raise ValueError("review contains an invalid decision value")
    try: confidence=float(item["reviewer_confidence"])
    except (TypeError,ValueError) as exc: raise ValueError("reviewer_confidence must be numeric") from exc
    if not 0 <= confidence <= 1: raise ValueError("reviewer_confidence must be 0..1")
    if slot not in {"reviewer_1","reviewer_2"}: raise ValueError("reviewer slot must be reviewer_1 or reviewer_2")


def import_review(decisions_path: str | Path, reviewer_slot: str, annotations_path: str | Path, review_dir: str | Path) -> dict[str, Any]:
    """Append a complete independent reviewer submission; never overwrite a prior one."""
    root=Path(review_dir); paths=_paths(root); destination=paths["r1"] if reviewer_slot=="reviewer_1" else paths["r2"]
    if destination.exists(): raise ValueError(f"{reviewer_slot} submission already exists; preserve the audit trail")
    decisions=load_jsonl(decisions_path); annotations=load_jsonl(annotations_path); known={a["annotation_id"] for a in annotations}
    if len(decisions)!=len(annotations) or len({d.get("annotation_id") for d in decisions})!=len(decisions): raise ValueError("review submission must contain one unique decision per annotation")
    for decision in decisions: _validate_decision(decision,reviewer_slot,known)
    destination.parent.mkdir(parents=True,exist_ok=True); write_jsonl(destination,decisions)
    return build_status(annotations,root)


def conflicts(annotations: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    one={r["annotation_id"]:r for r in _load(_paths(root)["r1"])}; two={r["annotation_id"]:r for r in _load(_paths(root)["r2"])}; rows=[]
    for annotation in annotations:
        ident=annotation["annotation_id"]
        if ident not in one or ident not in two: continue
        fields=[field for field in _AGREEMENT_FIELDS if one[ident][field]!=two[ident][field]]
        if fields: rows.append({"annotation_id":ident,"paper_id":annotation["paper_id"],"disagreement_fields":fields,"reviewer_1":one[ident],"reviewer_2":two[ident]})
    return rows


def build_adjudication_queue(annotations_path: str | Path, review_dir: str | Path) -> list[dict[str, Any]]:
    annotations=load_jsonl(annotations_path); root=Path(review_dir); rows=conflicts(annotations,root); _csv(rows,_paths(root)["conflicts"]); _csv(rows,root / "adjudication_packet.csv"); build_status(annotations,root); return rows


def adjudicate(decisions_path: str | Path, annotations_path: str | Path, review_dir: str | Path) -> dict[str, Any]:
    """Append final decisions for conflicts without editing machine or reviewer records."""
    root=Path(review_dir); paths=_paths(root)
    if paths["adjudications"].exists(): raise ValueError("adjudications already exist; preserve the audit trail")
    annotations=load_jsonl(annotations_path); pending={r["annotation_id"] for r in conflicts(annotations,root)}; decisions=load_jsonl(decisions_path)
    required={"annotation_id","adjudicator_id","final_gold_label","final_species","final_study_design","final_causal_status","final_protocol_vs_result","final_evidence_strength","final_evidence_quote_verified","adjudication_notes","final_confidence","adjudicated_at"}
    if {d.get("annotation_id") for d in decisions} != pending: raise ValueError("adjudications must cover exactly the conflicted annotations")
    for d in decisions:
        if not required <= set(d) or not d["adjudicator_id"] or d["final_evidence_quote_verified"] not in {"yes","no"}: raise ValueError("invalid adjudication decision")
    write_jsonl(paths["adjudications"],decisions); return build_status(annotations,root)


def _kappa(a: list[str], b: list[str]) -> dict[str, float | int] | None:
    if not a: return None
    n=len(a); raw=sum(x==y for x,y in zip(a,b))/n; ca,cb=Counter(a),Counter(b); expected=sum(ca[x]/n*cb[x]/n for x in set(a)|set(b))
    return {"n":n,"raw_agreement":raw,"cohens_kappa":1.0 if raw==expected==1 else (raw-expected)/(1-expected)}


def build_status(annotations: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    paths=_paths(root); one={r["annotation_id"]:r for r in _load(paths["r1"])}; two={r["annotation_id"]:r for r in _load(paths["r2"])}; adj={r["annotation_id"]:r for r in _load(paths["adjudications"])}; ids={a["annotation_id"] for a in annotations}; both=set(one)&set(two); conflict_rows=conflicts(annotations,root); conflict_ids={r["annotation_id"] for r in conflict_rows}
    agreement={field:_kappa([one[i][field] for i in both],[two[i][field] for i in both]) for field in ("label_decision","species_decision","causal_status_decision","protocol_vs_result_decision")}
    final={i:(adj[i] if i in adj else one[i] if i in both and i not in conflict_ids else None) for i in ids}
    status={"total_annotations":len(ids),"unreviewed_count":len(ids-(set(one)|set(two))),"single_reviewed_count":len((set(one)|set(two))-both),"double_reviewed_count":len(both),"disagreement_count":len(conflict_ids),"adjudicated_count":len(adj),"evidence_quote_rejection_count":sum(r.get("evidence_quote_verified")=="no" for r in list(one.values())+list(two.values())),"label_changes_from_machine":sum(bool(final[i]) and final[i].get("final_gold_label",final[i].get("label_decision"))!=next(a for a in annotations if a["annotation_id"]==i)["gold_label"] for i in ids),"species_changes":sum(bool(final[i]) and final[i].get("final_species",final[i].get("species_decision"))!=next(a for a in annotations if a["annotation_id"]==i)["species"] for i in ids),"causal_status_changes":sum(bool(final[i]) and final[i].get("final_causal_status",final[i].get("causal_status_decision"))!=next(a for a in annotations if a["annotation_id"]==i)["causal_status"] for i in ids),"agreement":agreement}
    write_json(paths["status"],status); return status


def freeze_gate(annotations_path: str | Path, review_dir: str | Path, registry_path: str | Path | None = None) -> dict[str, Any]:
    annotations=load_jsonl(annotations_path); root=Path(review_dir); status=build_status(annotations,root); paths=_paths(root); conflicts_rows=conflicts(annotations,root); adj={r["annotation_id"]:r for r in _load(paths["adjudications"])}; one={r["annotation_id"]:r for r in _load(paths["r1"])}; two={r["annotation_id"]:r for r in _load(paths["r2"])}
    quotes_ok=all((adj[c["annotation_id"]].get("final_evidence_quote_verified")=="yes") if c["annotation_id"] in adj else one.get(c["annotation_id"],{}).get("evidence_quote_verified")==two.get(c["annotation_id"],{}).get("evidence_quote_verified")=="yes" for c in [{"annotation_id":a["annotation_id"]} for a in annotations])
    provenance_errors=validate_annotations(annotations_path,registry_path) if registry_path is not None else []
    ready=status["double_reviewed_count"]==len(annotations) and all(c["annotation_id"] in adj for c in conflicts_rows) and quotes_ok and not provenance_errors
    reasons=[] if ready else ["two independent reviews, resolved conflicts, verified final quotes, and valid provenance are required"]
    return {"READY_TO_FREEZE":ready,"review_status":status,"provenance_error_count":len(provenance_errors),"reasons":reasons}
