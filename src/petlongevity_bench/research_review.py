"""Review packet, split, and dashboard utilities for draft research datasets."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .datasets import validate_research_dataset
from .io import load_json, load_jsonl, write_json, write_jsonl


SPLIT_NAMES = ("draft_train", "draft_dev", "hidden_test_candidate")
HUMAN_REVIEWER_SLOTS = {"reviewer_a", "reviewer_b"}
LLM_REVIEWER_SLOT = "llm_reviewer"
REVIEWER_SLOTS = {*HUMAN_REVIEWER_SLOTS, LLM_REVIEWER_SLOT}
REVIEW_FIELDS = (
    "label",
    "study_design",
    "outcome",
    "intervention_type",
    "evidence_strength",
    "correlation_vs_causation",
    "protocol_vs_results",
    "evidence_quote_verified",
)
LABELS = {"supported", "contradicted", "insufficient"}
STUDY_DESIGNS = {"RCT", "controlled trial", "cohort", "observational", "case study", "in vitro", "review", "protocol"}
OUTCOMES = {"lifespan", "mortality", "cognition", "mobility", "metabolic", "renal", "cardiac", "cancer", "biomarker"}
INTERVENTION_TYPES = {"drug", "nutrient", "diet", "lifestyle", "biomarker-only"}
EVIDENCE_STRENGTHS = {"very_low", "low", "moderate", "high", "very_high"}
CAUSALITY = {"causal", "correlational", "unclear"}
PROTOCOL_RESULTS = {"protocol", "results", "not_applicable"}
QUOTE_VERIFIED = {"yes", "no"}


def _manifest_rows(manifest_path: str | Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_file = Path(manifest_path)
    manifest = load_json(manifest_file)
    papers = load_jsonl(manifest_file.parent / manifest.get("paper_registry_file", ""))
    pairs = load_jsonl(manifest_file.parent / manifest.get("claim_evidence_file", ""))
    return manifest_file, manifest, papers, pairs


def _paper_splits(papers: list[dict[str, Any]], seed: str) -> dict[str, list[str]]:
    ordered = sorted(
        (str(paper["paper_id"]) for paper in papers),
        key=lambda paper_id: hashlib.sha256(f"{seed}|{paper_id}".encode("utf-8")).hexdigest(),
    )
    n = len(ordered)
    n_train = round(n * 0.60)
    n_dev = round(n * 0.20)
    if n >= 3:
        n_train = max(1, min(n_train, n - 2))
        n_dev = max(1, min(n_dev, n - n_train - 1))
    else:
        n_train = max(1, n - 1)
        n_dev = 0
    return {
        "draft_train": ordered[:n_train],
        "draft_dev": ordered[n_train : n_train + n_dev],
        "hidden_test_candidate": ordered[n_train + n_dev :],
    }


def _load_optional_review(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {str(row.get("pair_id")): row for row in load_jsonl(path) if row.get("pair_id")}


def _review_path(root: Path, reviewer_slot: str) -> Path:
    if reviewer_slot not in REVIEWER_SLOTS:
        raise ValueError("reviewer slot must be reviewer_a, reviewer_b, or llm_reviewer")
    return root / f"{reviewer_slot}.jsonl"


def _packet_index(root: Path) -> dict[str, dict[str, Any]]:
    packet_path = root / "coordinator_packet.jsonl"
    if not packet_path.exists():
        raise ValueError("coordinator_packet.jsonl is required before importing reviews")
    return {str(row["pair_id"]): row for row in load_jsonl(packet_path)}


def validate_research_review_submission(submission_path: str | Path, review_dir: str | Path) -> list[dict[str, Any]]:
    """Validate one complete abstract reviewer submission without importing it."""
    root = Path(review_dir)
    packet = _packet_index(root)
    rows = load_jsonl(submission_path)
    errors: list[dict[str, Any]] = []
    pair_ids = [str(row.get("pair_id")) for row in rows]
    if set(pair_ids) != set(packet) or len(pair_ids) != len(set(pair_ids)):
        errors.append({"row": None, "pair_id": None, "path": "pair_id", "message": "submission must contain one unique decision per review pair"})
    checks = {
        "label": LABELS,
        "study_design": STUDY_DESIGNS,
        "outcome": OUTCOMES,
        "intervention_type": INTERVENTION_TYPES,
        "evidence_strength": EVIDENCE_STRENGTHS,
        "correlation_vs_causation": CAUSALITY,
        "protocol_vs_results": PROTOCOL_RESULTS,
        "evidence_quote_verified": QUOTE_VERIFIED,
    }
    required = {"pair_id", "reviewer_id", "notes", *checks}
    for index, row in enumerate(rows):
        pair_id = str(row.get("pair_id"))
        if not required <= set(row):
            errors.append({"row": index, "pair_id": pair_id, "path": "record", "message": "review decision is missing required fields"})
        if pair_id not in packet:
            errors.append({"row": index, "pair_id": pair_id, "path": "pair_id", "message": "unknown review pair"})
        if not isinstance(row.get("reviewer_id"), str) or not row["reviewer_id"].strip():
            errors.append({"row": index, "pair_id": pair_id, "path": "reviewer_id", "message": "reviewer_id is required"})
        for field, allowed in checks.items():
            if row.get(field) not in allowed:
                errors.append({"row": index, "pair_id": pair_id, "path": field, "message": f"{field} has an invalid value"})
        if not isinstance(row.get("notes"), str):
            errors.append({"row": index, "pair_id": pair_id, "path": "notes", "message": "notes must be a string"})
    return errors


def import_research_review(submission_path: str | Path, reviewer_slot: str, review_dir: str | Path) -> dict[str, Any]:
    """Import one complete reviewer submission into an append-only reviewer slot."""
    root = Path(review_dir)
    destination = _review_path(root, reviewer_slot)
    if destination.exists():
        raise ValueError(f"{reviewer_slot} already exists; preserve the audit trail")
    errors = validate_research_review_submission(submission_path, root)
    if errors:
        raise ValueError(f"invalid review submission: {errors[0]['message']}")
    write_jsonl(destination, load_jsonl(submission_path))
    if reviewer_slot == LLM_REVIEWER_SLOT:
        build_llm_adjudication_queue(root)
        return llm_review_status(root)
    build_research_adjudication_queue(root)
    if reviewer_slot == "reviewer_a" and (root / f"{LLM_REVIEWER_SLOT}.jsonl").exists():
        build_llm_adjudication_queue(root, reviewer_slot)
    return research_review_status(root)


def _agreement_conflicts(reviewer_a: dict[str, Any], reviewer_b: dict[str, Any]) -> list[str]:
    return [field for field in REVIEW_FIELDS if reviewer_a.get(field) != reviewer_b.get(field)]


def _paired_review_conflicts(review_dir: Path, left_slot: str, right_slot: str) -> list[dict[str, Any]]:
    root = Path(review_dir)
    packet = _packet_index(root)
    reviewer_a = _load_optional_review(_review_path(root, left_slot))
    reviewer_b = _load_optional_review(_review_path(root, right_slot))
    rows = []
    for pair_id in sorted(set(reviewer_a) & set(reviewer_b)):
        fields = _agreement_conflicts(reviewer_a[pair_id], reviewer_b[pair_id])
        if not fields:
            continue
        rows.append({
            "pair_id": pair_id,
            "paper_id": packet[pair_id]["paper_id"],
            "pmid": packet[pair_id].get("pmid"),
            "title": packet[pair_id].get("title"),
            "claim_text": packet[pair_id].get("claim_text"),
            "supporting_span": packet[pair_id].get("supporting_span"),
            "disagreement_fields": fields,
            "left_slot": left_slot,
            "right_slot": right_slot,
            left_slot: reviewer_a[pair_id],
            right_slot: reviewer_b[pair_id],
            "reviewer_a": reviewer_a[pair_id],
            "reviewer_b": reviewer_b[pair_id],
        })
    return rows


def research_review_conflicts(review_dir: str | Path) -> list[dict[str, Any]]:
    """Return two-human review disagreements that require gold adjudication."""
    return _paired_review_conflicts(Path(review_dir), "reviewer_a", "reviewer_b")


def llm_review_conflicts(review_dir: str | Path, human_slot: str = "reviewer_a") -> list[dict[str, Any]]:
    """Return human/LLM disagreements that require silver adjudication."""
    if human_slot not in HUMAN_REVIEWER_SLOTS:
        raise ValueError("human_slot must be reviewer_a or reviewer_b")
    return _paired_review_conflicts(Path(review_dir), human_slot, LLM_REVIEWER_SLOT)


def _write_adjudication_queue(root: Path, rows: list[dict[str, Any]], stem: str) -> list[dict[str, Any]]:
    write_jsonl(root / f"{stem}.jsonl", rows)
    _write_csv(
        root / f"{stem}.csv",
        [
            {
                "pair_id": row["pair_id"],
                "paper_id": row["paper_id"],
                "pmid": row["pmid"],
                "title": row["title"],
                "claim_text": row["claim_text"],
                "evidence_text": row["supporting_span"]["text"],
                "disagreement_fields": "|".join(row["disagreement_fields"]),
                "left_slot": row["left_slot"],
                "right_slot": row["right_slot"],
                "left_label": row["reviewer_a"].get("label"),
                "right_label": row["reviewer_b"].get("label"),
                "reviewer_a_label": row["reviewer_a"].get("label"),
                "reviewer_b_label": row["reviewer_b"].get("label"),
            }
            for row in rows
        ],
    )
    return rows


def build_research_adjudication_queue(review_dir: str | Path) -> list[dict[str, Any]]:
    """Write JSONL/CSV adjudication packets for current two-human review conflicts."""
    root = Path(review_dir)
    return _write_adjudication_queue(root, research_review_conflicts(root), "adjudication_packet")


def build_llm_adjudication_queue(review_dir: str | Path, human_slot: str = "reviewer_a") -> list[dict[str, Any]]:
    """Write JSONL/CSV adjudication packets for current human/LLM review conflicts."""
    root = Path(review_dir)
    return _write_adjudication_queue(root, llm_review_conflicts(root, human_slot), "llm_adjudication_packet")


def _validate_adjudication_submission(submission_path: str | Path, conflicts: set[str]) -> list[dict[str, Any]]:
    rows = load_jsonl(submission_path)
    errors: list[dict[str, Any]] = []
    pair_ids = [str(row.get("pair_id")) for row in rows]
    if set(pair_ids) != conflicts or len(pair_ids) != len(set(pair_ids)):
        errors.append({"row": None, "pair_id": None, "path": "pair_id", "message": "adjudication must cover exactly the current conflicted pairs"})
    checks = {
        "final_label": LABELS,
        "final_study_design": STUDY_DESIGNS,
        "final_outcome": OUTCOMES,
        "final_intervention_type": INTERVENTION_TYPES,
        "final_evidence_strength": EVIDENCE_STRENGTHS,
        "final_correlation_vs_causation": CAUSALITY,
        "final_protocol_vs_results": PROTOCOL_RESULTS,
        "final_evidence_quote_verified": QUOTE_VERIFIED,
    }
    required = {"pair_id", "adjudicator_id", "adjudication_notes", "adjudicated_at", *checks}
    for index, row in enumerate(rows):
        pair_id = str(row.get("pair_id"))
        if not required <= set(row):
            errors.append({"row": index, "pair_id": pair_id, "path": "record", "message": "adjudication is missing required fields"})
        if not isinstance(row.get("adjudicator_id"), str) or not row["adjudicator_id"].strip():
            errors.append({"row": index, "pair_id": pair_id, "path": "adjudicator_id", "message": "adjudicator_id is required"})
        if not isinstance(row.get("adjudication_notes"), str):
            errors.append({"row": index, "pair_id": pair_id, "path": "adjudication_notes", "message": "adjudication_notes must be a string"})
        if not isinstance(row.get("adjudicated_at"), str) or not row["adjudicated_at"].strip():
            errors.append({"row": index, "pair_id": pair_id, "path": "adjudicated_at", "message": "adjudicated_at is required"})
        for field, allowed in checks.items():
            if row.get(field) not in allowed:
                errors.append({"row": index, "pair_id": pair_id, "path": field, "message": f"{field} has an invalid value"})
    return errors


def validate_research_adjudication_submission(submission_path: str | Path, review_dir: str | Path) -> list[dict[str, Any]]:
    """Validate gold adjudicator decisions for exactly the current two-human disagreement set."""
    root = Path(review_dir)
    conflicts = {row["pair_id"] for row in research_review_conflicts(root)}
    return _validate_adjudication_submission(submission_path, conflicts)


def validate_llm_adjudication_submission(
    submission_path: str | Path,
    review_dir: str | Path,
    human_slot: str = "reviewer_a",
) -> list[dict[str, Any]]:
    """Validate silver adjudicator decisions for exactly the current human/LLM disagreement set."""
    root = Path(review_dir)
    conflicts = {row["pair_id"] for row in llm_review_conflicts(root, human_slot)}
    return _validate_adjudication_submission(submission_path, conflicts)


def adjudicate_research_review(submission_path: str | Path, review_dir: str | Path) -> dict[str, Any]:
    """Import adjudicator decisions for conflicts without overwriting reviewer files."""
    root = Path(review_dir)
    destination = root / "adjudications.jsonl"
    if destination.exists():
        raise ValueError("adjudications already exist; preserve the audit trail")
    errors = validate_research_adjudication_submission(submission_path, root)
    if errors:
        raise ValueError(f"invalid adjudication submission: {errors[0]['message']}")
    write_jsonl(destination, load_jsonl(submission_path))
    return research_review_status(root)


def adjudicate_llm_review(submission_path: str | Path, review_dir: str | Path, human_slot: str = "reviewer_a") -> dict[str, Any]:
    """Import adjudicator decisions for human/LLM conflicts without overwriting reviewer files."""
    root = Path(review_dir)
    destination = root / "llm_adjudications.jsonl"
    if destination.exists():
        raise ValueError("llm_adjudications already exist; preserve the audit trail")
    errors = validate_llm_adjudication_submission(submission_path, root, human_slot)
    if errors:
        raise ValueError(f"invalid LLM adjudication submission: {errors[0]['message']}")
    write_jsonl(destination, load_jsonl(submission_path))
    return llm_review_status(root, human_slot)


def _final_decisions_for_slots(
    review_dir: Path,
    left_slot: str,
    right_slot: str,
    adjudications_file: str,
    consensus_id: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    packet = _packet_index(review_dir)
    reviewer_a = _load_optional_review(_review_path(review_dir, left_slot))
    reviewer_b = _load_optional_review(_review_path(review_dir, right_slot))
    adjudications = _load_optional_review(review_dir / adjudications_file)
    final: dict[str, dict[str, Any]] = {}
    for pair_id in packet:
        if pair_id not in reviewer_a or pair_id not in reviewer_b:
            continue
        conflict_fields = _agreement_conflicts(reviewer_a[pair_id], reviewer_b[pair_id])
        if conflict_fields:
            if pair_id in adjudications:
                adj = adjudications[pair_id]
                final[pair_id] = {
                    "label": adj["final_label"],
                    "study_design": adj["final_study_design"],
                    "outcome": adj["final_outcome"],
                    "intervention_type": adj["final_intervention_type"],
                    "evidence_strength": adj["final_evidence_strength"],
                    "correlation_vs_causation": adj["final_correlation_vs_causation"],
                    "protocol_vs_results": adj["final_protocol_vs_results"],
                    "evidence_quote_verified": adj["final_evidence_quote_verified"],
                    "notes": adj["adjudication_notes"],
                    "adjudicator_id": adj["adjudicator_id"],
                }
            continue
        final[pair_id] = {
            **{field: reviewer_a[pair_id][field] for field in REVIEW_FIELDS},
            "notes": f"Consensus without conflict. {left_slot}: "
            + reviewer_a[pair_id].get("notes", "")
            + f" {right_slot}: "
            + reviewer_b[pair_id].get("notes", ""),
            "adjudicator_id": consensus_id,
        }
    return packet, reviewer_a, reviewer_b, final


def _final_decisions(review_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    return _final_decisions_for_slots(review_dir, "reviewer_a", "reviewer_b", "adjudications.jsonl", "consensus-no-conflict")


def _promote_reviewed_research_dataset(
    manifest_file: Path,
    papers: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    review_dir: Path,
    output_dir: str | Path,
    dataset_id: str,
    dataset_status: str,
    left_slot: str,
    right_slot: str,
    adjudications_file: str,
    consensus_id: str,
    description: str,
) -> dict[str, Any]:
    _, reviewer_a, reviewer_b, final = _final_decisions_for_slots(review_dir, left_slot, right_slot, adjudications_file, consensus_id)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    promoted_pairs = []
    for pair in pairs:
        pair_id = str(pair["pair_id"])
        decision = final[pair_id]
        if decision["evidence_quote_verified"] != "yes":
            raise ValueError("cannot promote records with unverified evidence quotes")
        promoted = dict(pair)
        promoted.update({
            "label": decision["label"],
            "study_design": decision["study_design"],
            "outcome": decision["outcome"],
            "intervention_type": decision["intervention_type"],
            "evidence_strength": decision["evidence_strength"],
            "correlation_vs_causation": decision["correlation_vs_causation"],
            "protocol_vs_results": decision["protocol_vs_results"],
            "review": {
                "annotator_a": {"annotator_id": reviewer_a[pair_id]["reviewer_id"]},
                "annotator_b": {"annotator_id": reviewer_b[pair_id]["reviewer_id"]},
                "adjudicator": {"annotator_id": decision["adjudicator_id"]},
                "status": "adjudicated",
                "notes": decision["notes"],
            },
        })
        promoted_pairs.append(promoted)
    write_jsonl(output / "paper_registry.jsonl", papers)
    write_jsonl(output / "claim_evidence.jsonl", promoted_pairs)
    write_json(output / "research_dataset_manifest.json", {
        "dataset_id": dataset_id,
        "schema_version": "1.0",
        "dataset_status": dataset_status,
        "paper_registry_file": "paper_registry.jsonl",
        "claim_evidence_file": "claim_evidence.jsonl",
        "description": description,
        "license": "Metadata and abstracts retain their original source terms; reviewer annotations are CC0.",
    })
    split_path = review_dir / "splits.json"
    if split_path.exists():
        export_m2_baseline_splits(output / "claim_evidence.jsonl", split_path, output / "m2_splits")
    errors = validate_research_dataset(output / "research_dataset_manifest.json")
    if errors:
        raise ValueError(f"promoted {dataset_status} dataset is invalid: {errors[0]['message']}")
    return {"output_dir": str(output), "dataset_id": dataset_id, "dataset_status": dataset_status, "papers": len(papers), "pairs": len(promoted_pairs), "m2_splits": str(output / "m2_splits")}


def promote_research_gold(
    manifest_path: str | Path,
    review_dir: str | Path,
    output_dir: str | Path,
    dataset_id: str = "petlongevity-abstract-gold-v0.4",
) -> dict[str, Any]:
    """Promote fully reviewed abstract pairs to a gold research dataset."""
    manifest_file, _, papers, pairs = _manifest_rows(manifest_path)
    root = Path(review_dir)
    status = research_review_status(root, {str(pair["pair_id"]) for pair in pairs})
    if not status["READY_TO_FREEZE"]:
        raise ValueError("research review is not ready to promote")
    return _promote_reviewed_research_dataset(
        manifest_file,
        papers,
        pairs,
        root,
        output_dir,
        dataset_id,
        "gold",
        "reviewer_a",
        "reviewer_b",
        "adjudications.jsonl",
        "consensus-no-conflict",
        f"Human-reviewed and adjudicated abstract claim/evidence records promoted from {manifest_file}.",
    )


def promote_research_silver(
    manifest_path: str | Path,
    review_dir: str | Path,
    output_dir: str | Path,
    dataset_id: str = "petlongevity-abstract-silver-v0.4",
    human_slot: str = "reviewer_a",
) -> dict[str, Any]:
    """Promote one human plus one LLM review to a silver research benchmark."""
    if human_slot not in HUMAN_REVIEWER_SLOTS:
        raise ValueError("human_slot must be reviewer_a or reviewer_b")
    manifest_file, _, papers, pairs = _manifest_rows(manifest_path)
    root = Path(review_dir)
    status = llm_review_status(root, human_slot, {str(pair["pair_id"]) for pair in pairs})
    if not status["READY_FOR_SILVER"]:
        raise ValueError("LLM-assisted research review is not ready to promote")
    return _promote_reviewed_research_dataset(
        manifest_file,
        papers,
        pairs,
        root,
        output_dir,
        dataset_id,
        "silver",
        human_slot,
        LLM_REVIEWER_SLOT,
        "llm_adjudications.jsonl",
        "human-llm-consensus-no-conflict",
        f"Human plus LLM-reviewed abstract claim/evidence records promoted from {manifest_file}.",
    )


def _m2_row(pair: dict[str, Any]) -> dict[str, Any]:
    trap_type = "none"
    if pair.get("label") != "supported" and "species" in str(pair.get("review", {}).get("notes", "")).lower():
        trap_type = "species_transfer"
    elif pair.get("label") != "supported" and pair.get("outcome") not in {"lifespan", "mortality"}:
        trap_type = "surrogate_overclaim"
    return {
        "item_id": pair["pair_id"],
        "claim": pair["claim_text"],
        "label": pair["label"],
        "trap_type": trap_type,
        "risk_weight": 3.0 if trap_type != "none" else 1.0,
        "paper_id": pair["paper_id"],
        "publication_date": pair["publication_date"],
        "species": pair["species"],
    }


def export_m2_baseline_splits(claim_evidence_path: str | Path, splits_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Export reviewed claim/evidence pairs as M2 scoring inputs by paper-level split."""
    pairs = load_jsonl(claim_evidence_path)
    by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_paper[pair["paper_id"]].append(pair)
    splits = load_json(splits_path)["splits"]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name in SPLIT_NAMES:
        rows = [_m2_row(pair) for paper_id in splits.get(name, []) for pair in by_paper.get(paper_id, [])]
        write_jsonl(output / f"{name}_m2_gold.jsonl", rows)
        counts[name] = len(rows)
    write_json(output / "m2_split_manifest.json", {"source": str(claim_evidence_path), "splits": counts})
    return {"output_dir": str(output), "splits": counts}


def research_review_status(output_dir: str | Path, pair_ids: set[str] | None = None) -> dict[str, Any]:
    """Summarize independent-review progress for a draft review workspace."""
    root = Path(output_dir)
    packet_path = root / "coordinator_packet.jsonl"
    if pair_ids is None:
        pair_ids = {str(row["pair_id"]) for row in load_jsonl(packet_path)} if packet_path.exists() else set()
    reviewer_a = _load_optional_review(root / "reviewer_a.jsonl")
    reviewer_b = _load_optional_review(root / "reviewer_b.jsonl")
    adjudications = _load_optional_review(root / "adjudications.jsonl")
    reviewed_a = pair_ids & set(reviewer_a)
    reviewed_b = pair_ids & set(reviewer_b)
    paired = reviewed_a & reviewed_b
    conflicts = {pair_id for pair_id in paired if _agreement_conflicts(reviewer_a[pair_id], reviewer_b[pair_id])}
    missing_adjudication = conflicts - set(adjudications)
    consensus_quote_failures = {
        pair_id
        for pair_id in paired - conflicts
        if reviewer_a[pair_id].get("evidence_quote_verified") != "yes" or reviewer_b[pair_id].get("evidence_quote_verified") != "yes"
    }
    adjudication_quote_failures = {
        pair_id
        for pair_id in conflicts & set(adjudications)
        if adjudications[pair_id].get("final_evidence_quote_verified") != "yes"
    }
    total = len(pair_ids)
    return {
        "total_pairs": total,
        "reviewed_by_a": len(reviewed_a),
        "reviewed_by_b": len(reviewed_b),
        "paired_reviews": len(paired),
        "conflicts": len(conflicts),
        "adjudicated_conflicts": len(conflicts - missing_adjudication),
        "missing_adjudication": len(missing_adjudication),
        "final_quote_rejection_count": len(consensus_quote_failures | adjudication_quote_failures),
        "unreviewed_by_a": total - len(reviewed_a),
        "unreviewed_by_b": total - len(reviewed_b),
        "READY_TO_FREEZE": total > 0 and len(reviewed_a) == total and len(reviewed_b) == total and not missing_adjudication and not consensus_quote_failures and not adjudication_quote_failures,
    }


def llm_review_status(output_dir: str | Path, human_slot: str = "reviewer_a", pair_ids: set[str] | None = None) -> dict[str, Any]:
    """Summarize human/LLM review progress for a silver benchmark workspace."""
    if human_slot not in HUMAN_REVIEWER_SLOTS:
        raise ValueError("human_slot must be reviewer_a or reviewer_b")
    root = Path(output_dir)
    packet_path = root / "coordinator_packet.jsonl"
    if pair_ids is None:
        pair_ids = {str(row["pair_id"]) for row in load_jsonl(packet_path)} if packet_path.exists() else set()
    human_reviews = _load_optional_review(_review_path(root, human_slot))
    llm_reviews = _load_optional_review(_review_path(root, LLM_REVIEWER_SLOT))
    adjudications = _load_optional_review(root / "llm_adjudications.jsonl")
    reviewed_human = pair_ids & set(human_reviews)
    reviewed_llm = pair_ids & set(llm_reviews)
    paired = reviewed_human & reviewed_llm
    conflicts = {pair_id for pair_id in paired if _agreement_conflicts(human_reviews[pair_id], llm_reviews[pair_id])}
    missing_adjudication = conflicts - set(adjudications)
    consensus_quote_failures = {
        pair_id
        for pair_id in paired - conflicts
        if human_reviews[pair_id].get("evidence_quote_verified") != "yes" or llm_reviews[pair_id].get("evidence_quote_verified") != "yes"
    }
    adjudication_quote_failures = {
        pair_id
        for pair_id in conflicts & set(adjudications)
        if adjudications[pair_id].get("final_evidence_quote_verified") != "yes"
    }
    total = len(pair_ids)
    return {
        "total_pairs": total,
        "human_slot": human_slot,
        "llm_slot": LLM_REVIEWER_SLOT,
        "reviewed_by_human": len(reviewed_human),
        "reviewed_by_llm": len(reviewed_llm),
        "paired_reviews": len(paired),
        "conflicts": len(conflicts),
        "adjudicated_conflicts": len(conflicts - missing_adjudication),
        "missing_adjudication": len(missing_adjudication),
        "final_quote_rejection_count": len(consensus_quote_failures | adjudication_quote_failures),
        "unreviewed_by_human": total - len(reviewed_human),
        "unreviewed_by_llm": total - len(reviewed_llm),
        "READY_FOR_SILVER": total > 0 and len(reviewed_human) == total and len(reviewed_llm) == total and not missing_adjudication and not consensus_quote_failures and not adjudication_quote_failures,
    }


def _flat_row(packet: dict[str, Any], include_draft: bool) -> dict[str, Any]:
    row = {
        "pair_id": packet["pair_id"],
        "paper_id": packet["paper_id"],
        "pmid": packet.get("pmid"),
        "title": packet.get("title"),
        "publication_date": packet.get("publication_date"),
        "species": "|".join(packet.get("species") or []),
        "target_category": packet.get("target_category"),
        "claim_text": packet.get("claim_text"),
        "evidence_text": packet.get("supporting_span", {}).get("text"),
        "provenance_url": packet.get("provenance_url"),
        "source_text_path": packet.get("source_text_path"),
    }
    if include_draft:
        row |= {
            "machine_draft_label": packet.get("machine_draft", {}).get("label"),
            "machine_draft_study_design": packet.get("machine_draft", {}).get("study_design"),
            "machine_draft_outcome": packet.get("machine_draft", {}).get("outcome"),
            "machine_draft_intervention_type": packet.get("machine_draft", {}).get("intervention_type"),
            "machine_draft_evidence_strength": packet.get("machine_draft", {}).get("evidence_strength"),
        }
    return row


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row}) or ["pair_id"]
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_review_html(path: Path, packets: list[dict[str, Any]]) -> None:
    safe_data = json.dumps(packets, ensure_ascii=False).replace("</", "<\\/")
    path.write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PetLongevity Draft Review</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; color: #172026; background: #f7f7f4; }
    header, main { max-width: 1040px; margin: 0 auto; padding: 20px; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: center; border-bottom: 1px solid #d8d8d0; }
    h1 { font-size: 20px; margin: 0; }
    button, select, textarea, input { font: inherit; }
    button { border: 1px solid #1f5f6b; background: #1f5f6b; color: white; padding: 8px 12px; border-radius: 6px; cursor: pointer; }
    button.secondary { background: white; color: #1f5f6b; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .meta, .span, .claim, .form { background: white; border: 1px solid #d8d8d0; border-radius: 8px; padding: 14px; margin: 14px 0; }
    .meta dl { display: grid; grid-template-columns: 150px 1fr; gap: 6px 12px; margin: 0; }
    .meta dt { color: #566068; }
    .claim { font-size: 18px; line-height: 1.45; }
    .span { line-height: 1.5; border-left: 4px solid #8a6f20; }
    label { display: block; font-weight: 700; margin-top: 12px; }
    select, textarea, input { width: 100%; box-sizing: border-box; margin-top: 6px; padding: 8px; border: 1px solid #b9b9b0; border-radius: 6px; background: white; }
    textarea { min-height: 76px; }
    .progress { color: #566068; }
  </style>
</head>
<body>
<header>
  <h1>PetLongevity Draft Review</h1>
  <div class="toolbar">
    <button class="secondary" id="prev">Previous</button>
    <button class="secondary" id="next">Next</button>
    <button id="download">Download JSONL</button>
  </div>
</header>
<main>
  <p class="progress" id="progress"></p>
  <section class="meta"><dl id="meta"></dl></section>
  <section class="claim" id="claim"></section>
  <section class="span" id="span"></section>
  <section class="form">
    <label>Label<select id="label"><option value=""></option><option>supported</option><option>contradicted</option><option>insufficient</option></select></label>
    <label>Study Design<select id="study_design"><option value=""></option><option>RCT</option><option>controlled trial</option><option>cohort</option><option>observational</option><option>case study</option><option>in vitro</option><option>review</option><option>protocol</option></select></label>
    <label>Outcome<select id="outcome"><option value=""></option><option>lifespan</option><option>mortality</option><option>cognition</option><option>mobility</option><option>metabolic</option><option>renal</option><option>cardiac</option><option>cancer</option><option>biomarker</option></select></label>
    <label>Intervention Type<select id="intervention_type"><option value=""></option><option>drug</option><option>nutrient</option><option>diet</option><option>lifestyle</option><option>biomarker-only</option></select></label>
    <label>Evidence Strength<select id="strength"><option value=""></option><option>very_low</option><option>low</option><option>moderate</option><option>high</option><option>very_high</option></select></label>
    <label>Causality<select id="correlation_vs_causation"><option value=""></option><option>causal</option><option>correlational</option><option>unclear</option></select></label>
    <label>Protocol vs Results<select id="protocol_vs_results"><option value=""></option><option>protocol</option><option>results</option><option>not_applicable</option></select></label>
    <label>Exact Quote Verified<select id="evidence_quote_verified"><option value=""></option><option>yes</option><option>no</option></select></label>
    <label>Notes<textarea id="notes"></textarea></label>
    <label>Reviewer ID<input id="reviewer" autocomplete="off"></label>
  </section>
</main>
<script>
const packets = DATA_PLACEHOLDER;
const key = "petlongevity-draft-review";
let index = 0;
let answers = JSON.parse(localStorage.getItem(key) || "{}");
function saveCurrent() {
  const item = packets[index];
  if (!item) return;
  answers[item.pair_id] = {
    pair_id: item.pair_id,
    label: document.getElementById("label").value,
    study_design: document.getElementById("study_design").value,
    outcome: document.getElementById("outcome").value,
    intervention_type: document.getElementById("intervention_type").value,
    evidence_strength: document.getElementById("strength").value,
    correlation_vs_causation: document.getElementById("correlation_vs_causation").value,
    protocol_vs_results: document.getElementById("protocol_vs_results").value,
    evidence_quote_verified: document.getElementById("evidence_quote_verified").value,
    notes: document.getElementById("notes").value,
    reviewer_id: document.getElementById("reviewer").value
  };
  localStorage.setItem(key, JSON.stringify(answers));
}
function render() {
  const item = packets[index];
  document.getElementById("progress").textContent = `${index + 1} / ${packets.length}`;
  document.getElementById("meta").innerHTML = ["pair_id","pmid","publication_date","species","target_category","title"].map(k => `<dt>${k}</dt><dd>${Array.isArray(item[k]) ? item[k].join(", ") : (item[k] || "")}</dd>`).join("");
  document.getElementById("claim").textContent = item.claim_text;
  document.getElementById("span").textContent = item.supporting_span.text;
  const answer = answers[item.pair_id] || {};
  document.getElementById("label").value = answer.label || "";
  document.getElementById("study_design").value = answer.study_design || "";
  document.getElementById("outcome").value = answer.outcome || "";
  document.getElementById("intervention_type").value = answer.intervention_type || "";
  document.getElementById("strength").value = answer.evidence_strength || "";
  document.getElementById("correlation_vs_causation").value = answer.correlation_vs_causation || "";
  document.getElementById("protocol_vs_results").value = answer.protocol_vs_results || "";
  document.getElementById("evidence_quote_verified").value = answer.evidence_quote_verified || "";
  document.getElementById("notes").value = answer.notes || "";
  document.getElementById("reviewer").value = answer.reviewer_id || "";
}
["label","study_design","outcome","intervention_type","strength","correlation_vs_causation","protocol_vs_results","evidence_quote_verified","notes","reviewer"].forEach(id => document.getElementById(id).addEventListener("change", saveCurrent));
document.getElementById("prev").onclick = () => { saveCurrent(); index = Math.max(0, index - 1); render(); };
document.getElementById("next").onclick = () => { saveCurrent(); index = Math.min(packets.length - 1, index + 1); render(); };
document.getElementById("download").onclick = () => {
  saveCurrent();
  const text = packets.map(item => JSON.stringify(answers[item.pair_id] || { pair_id: item.pair_id })).join("\\n") + "\\n";
  const blob = new Blob([text], { type: "application/jsonl" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "reviewer_submission.jsonl";
  a.click();
};
render();
</script>
</body>
</html>
""".replace("DATA_PLACEHOLDER", safe_data),
        encoding="utf-8",
        newline="\n",
    )


def _dashboard(
    manifest: dict[str, Any],
    papers: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    split_pairs: dict[str, list[dict[str, Any]]],
    corpus_registry: list[dict[str, Any]],
    validation_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    corpus_by_id = {row.get("paper_id"): row for row in corpus_registry}
    full_text = [paper["paper_id"] for paper in papers if corpus_by_id.get(paper["paper_id"], {}).get("full_text_available")]
    categories = Counter(corpus_by_id.get(paper["paper_id"], {}).get("target_category", "unknown") for paper in papers)
    species = Counter(species for paper in papers for species in paper.get("species", []))
    return {
        "dataset_id": manifest.get("dataset_id"),
        "dataset_status": manifest.get("dataset_status"),
        "n_papers": len(papers),
        "n_pairs": len(pairs),
        "validation_errors": len(validation_errors),
        "papers_by_species": dict(sorted(species.items())),
        "papers_by_target_category": dict(sorted(categories.items())),
        "pairs_by_label": dict(sorted(Counter(pair.get("label") for pair in pairs).items())),
        "pairs_by_study_design": dict(sorted(Counter(pair.get("study_design") for pair in pairs).items())),
        "pairs_by_outcome": dict(sorted(Counter(pair.get("outcome") for pair in pairs).items())),
        "pairs_by_intervention_type": dict(sorted(Counter(pair.get("intervention_type") for pair in pairs).items())),
        "full_text_available_papers": len(full_text),
        "lawful_fulltext_required_papers": len(papers) - len(full_text),
        "splits": {name: {"papers": len({pair["paper_id"] for pair in rows}), "pairs": len(rows)} for name, rows in split_pairs.items()},
    }


def _write_dashboard_markdown(path: Path, dashboard: dict[str, Any]) -> None:
    lines = [
        f"# {dashboard['dataset_id']} quality dashboard",
        "",
        f"- Papers: {dashboard['n_papers']}",
        f"- Claim/evidence draft pairs: {dashboard['n_pairs']}",
        f"- Validation errors: {dashboard['validation_errors']}",
        f"- Local rights-cleared full texts: {dashboard['full_text_available_papers']}",
        f"- Papers needing lawful full-text sourcing: {dashboard['lawful_fulltext_required_papers']}",
        "",
        "## Splits",
        "",
    ]
    for name, counts in dashboard["splits"].items():
        lines.append(f"- {name}: {counts['papers']} papers, {counts['pairs']} pairs")
    lines.extend(["", "## Target Categories", ""])
    for name, count in dashboard["papers_by_target_category"].items():
        lines.append(f"- {name}: {count}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def prepare_research_review(
    manifest_path: str | Path,
    output_dir: str | Path,
    corpus_registry_path: str | Path | None = None,
    split_seed: str | None = None,
) -> dict[str, Any]:
    """Create review, dashboard, and split artifacts for a draft research manifest."""
    manifest_file, manifest, papers, pairs = _manifest_rows(manifest_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    validation_errors = validate_research_dataset(manifest_file)
    paper_index = {paper["paper_id"]: paper for paper in papers}
    corpus_registry = load_jsonl(corpus_registry_path) if corpus_registry_path and Path(corpus_registry_path).exists() else []
    corpus_index = {row.get("paper_id"): row for row in corpus_registry}
    packets: list[dict[str, Any]] = []
    reviewer_packets: list[dict[str, Any]] = []
    for pair in pairs:
        paper = paper_index[pair["paper_id"]]
        corpus_row = corpus_index.get(pair["paper_id"], {})
        packet = {
            "pair_id": pair["pair_id"],
            "paper_id": pair["paper_id"],
            "pmid": paper.get("pmid"),
            "title": paper.get("title"),
            "publication_date": pair.get("publication_date"),
            "species": pair.get("species"),
            "target_category": corpus_row.get("target_category", "unknown"),
            "claim_text": pair.get("claim_text"),
            "supporting_span": pair.get("supporting_span"),
            "source_text_path": pair.get("source_text_path"),
            "source_text_sha256": pair.get("source_text_sha256"),
            "provenance_url": pair.get("provenance_url"),
            "machine_draft": {
                "label": pair.get("label"),
                "study_design": pair.get("study_design"),
                "outcome": pair.get("outcome"),
                "intervention_type": pair.get("intervention_type"),
                "evidence_strength": pair.get("evidence_strength"),
                "correlation_vs_causation": pair.get("correlation_vs_causation"),
                "protocol_vs_results": pair.get("protocol_vs_results"),
            },
        }
        packets.append(packet)
        reviewer_packets.append({key: value for key, value in packet.items() if key != "machine_draft"})
    write_jsonl(output / "coordinator_packet.jsonl", packets)
    write_jsonl(output / "reviewer_packet_blinded.jsonl", reviewer_packets)
    _write_csv(output / "coordinator_packet.csv", [_flat_row(packet, True) for packet in packets])
    _write_csv(output / "reviewer_packet_blinded.csv", [_flat_row(packet, False) for packet in reviewer_packets])
    _write_review_html(output / "reviewer_abstracts.html", reviewer_packets)

    seed = split_seed or str(manifest.get("dataset_id") or "petlongevity-draft")
    split_papers = _paper_splits(papers, seed)
    pair_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        pair_groups[pair["paper_id"]].append(pair)
    split_pairs = {name: [pair for paper_id in ids for pair in pair_groups[paper_id]] for name, ids in split_papers.items()}
    splits_dir = output / "splits"
    splits_dir.mkdir(exist_ok=True)
    for name, rows in split_pairs.items():
        write_jsonl(splits_dir / f"{name}.jsonl", rows)
    write_json(output / "splits.json", {"seed": seed, "splits": split_papers})

    dashboard = _dashboard(manifest, papers, pairs, split_pairs, corpus_registry, validation_errors)
    write_json(output / "quality_dashboard.json", dashboard)
    _write_dashboard_markdown(output / "quality_dashboard.md", dashboard)
    status = research_review_status(output, {str(pair["pair_id"]) for pair in pairs})
    status["validation_errors"] = len(validation_errors)
    write_json(output / "review_status.json", status)
    (output / "README.md").write_text(
        "# Draft abstract review workspace\n\n"
        "`reviewer_packet_blinded.*` and `reviewer_abstracts.html` omit machine draft labels. "
        "`coordinator_packet.*` keeps the draft labels separated for audit and triage. "
        "These files are human-review work items, not gold benchmark labels.\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "manifest": str(manifest_file),
        "output_dir": str(output),
        "papers": len(papers),
        "pairs": len(pairs),
        "validation_errors": len(validation_errors),
        "status": status,
        "dashboard": dashboard,
    }
