"""Prompt-packet builder for the abstract-review LLM reviewer slot."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io import load_jsonl, write_json, write_jsonl
from .research_review import (
    CAUSALITY,
    EVIDENCE_STRENGTHS,
    INTERVENTION_TYPES,
    LABELS,
    LLM_REVIEWER_SLOT,
    OUTCOMES,
    PROTOCOL_RESULTS,
    QUOTE_VERIFIED,
    STUDY_DESIGNS,
)


OUTPUT_FIELDS = (
    "pair_id",
    "reviewer_id",
    "label",
    "study_design",
    "outcome",
    "intervention_type",
    "evidence_strength",
    "correlation_vs_causation",
    "protocol_vs_results",
    "evidence_quote_verified",
    "notes",
)


def _allowed_values() -> dict[str, list[str]]:
    return {
        "label": sorted(LABELS),
        "study_design": sorted(STUDY_DESIGNS),
        "outcome": sorted(OUTCOMES),
        "intervention_type": sorted(INTERVENTION_TYPES),
        "evidence_strength": sorted(EVIDENCE_STRENGTHS),
        "correlation_vs_causation": sorted(CAUSALITY),
        "protocol_vs_results": sorted(PROTOCOL_RESULTS),
        "evidence_quote_verified": sorted(QUOTE_VERIFIED),
    }


def _response_schema(reviewer_id: str) -> dict[str, Any]:
    allowed = _allowed_values()
    properties: dict[str, Any] = {
        "pair_id": {"type": "string", "minLength": 1},
        "reviewer_id": {"const": reviewer_id},
        "notes": {"type": "string"},
    }
    for field, values in allowed.items():
        properties[field] = {"enum": values}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "PetLongevity-Bench llm_reviewer JSONL row",
        "type": "object",
        "additionalProperties": False,
        "required": list(OUTPUT_FIELDS),
        "properties": properties,
    }


def _safe_packet(row: dict[str, Any]) -> dict[str, Any]:
    clean = dict(row)
    clean.pop("machine_draft", None)
    return clean


def _instructions(reviewer_id: str) -> str:
    allowed = _allowed_values()
    return "\n".join(
        [
            "# PetLongevity-Bench LLM Abstract Review",
            "",
            f"Reviewer slot: `{LLM_REVIEWER_SLOT}`",
            f"Use reviewer_id: `{reviewer_id}`",
            "",
            "Return JSONL only: exactly one compact JSON object per input pair, with no markdown.",
            "Use only the displayed title, claim text, evidence text, and provenance fields.",
            "Do not use machine draft labels, outside knowledge, or unstated paper conclusions.",
            "Set `evidence_quote_verified` to `yes` only when the evidence text directly contains the quoted support.",
            "Use `insufficient` when the evidence text does not directly support or contradict the claim.",
            "",
            "Required output fields, in this order:",
            ", ".join(f"`{field}`" for field in OUTPUT_FIELDS),
            "",
            "Allowed values:",
            json.dumps(allowed, indent=2, sort_keys=True),
            "",
            "After combining chunk outputs, validate and import with:",
            "```bash",
            "petbench validate-research-review --submission llm_reviewer.jsonl --review-dir review/abstracts_300",
            "petbench import-research-review --submission llm_reviewer.jsonl --reviewer-slot llm_reviewer --review-dir review/abstracts_300",
            "```",
        ]
    )


def _chunk_prompt(rows: list[dict[str, Any]], index: int, total: int, reviewer_id: str) -> str:
    return "\n".join(
        [
            _instructions(reviewer_id),
            "",
            f"Chunk {index} of {total}.",
            f"Return exactly {len(rows)} JSONL rows.",
            "",
            "Input pairs:",
            "```json",
            json.dumps(rows, indent=2, sort_keys=True),
            "```",
        ]
    )


def build_llm_review_prompts(
    review_dir: str | Path,
    output_dir: str | Path,
    max_pairs_per_prompt: int = 20,
    reviewer_id: str = "llm-reviewer",
) -> dict[str, Any]:
    """Build chunked prompt files for producing an auditable llm_reviewer submission."""
    if max_pairs_per_prompt < 1:
        raise ValueError("max_pairs_per_prompt must be at least 1")
    root = Path(review_dir)
    packet_path = root / "reviewer_packet_blinded.jsonl"
    if not packet_path.exists():
        raise FileNotFoundError(f"{packet_path} does not exist")
    rows = [_safe_packet(row) for row in load_jsonl(packet_path)]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    instructions = _instructions(reviewer_id)
    (output / "instructions.md").write_text(instructions + "\n", encoding="utf-8", newline="\n")
    write_json(output / "response_schema.json", _response_schema(reviewer_id))
    chunks = [rows[i : i + max_pairs_per_prompt] for i in range(0, len(rows), max_pairs_per_prompt)]
    prompt_files = []
    for index, chunk in enumerate(chunks, 1):
        path = output / f"chunk_{index:03d}_prompt.md"
        path.write_text(_chunk_prompt(chunk, index, len(chunks), reviewer_id) + "\n", encoding="utf-8", newline="\n")
        prompt_files.append({"path": str(path), "pairs": len(chunk)})
    manifest = {
        "reviewer_slot": LLM_REVIEWER_SLOT,
        "reviewer_id": reviewer_id,
        "source_packet": str(packet_path),
        "n_pairs": len(rows),
        "max_pairs_per_prompt": max_pairs_per_prompt,
        "n_chunks": len(prompt_files),
        "prompt_files": prompt_files,
        "response_schema_file": "response_schema.json",
    }
    write_json(output / "llm_review_prompt_manifest.json", manifest)
    return manifest


def _validate_llm_rows(rows: list[dict[str, Any]], expected_pair_ids: list[str], reviewer_id: str) -> list[dict[str, Any]]:
    allowed = _allowed_values()
    expected = set(expected_pair_ids)
    seen: set[str] = set()
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        pair_id = str(row.get("pair_id"))
        keys = set(row)
        if keys != set(OUTPUT_FIELDS):
            errors.append({"row": index, "pair_id": pair_id, "path": "record", "message": "LLM row must contain exactly the required output fields"})
        if row.get("reviewer_id") != reviewer_id:
            errors.append({"row": index, "pair_id": pair_id, "path": "reviewer_id", "message": f"reviewer_id must be {reviewer_id}"})
        if pair_id not in expected:
            errors.append({"row": index, "pair_id": pair_id, "path": "pair_id", "message": "unknown review pair"})
        if pair_id in seen:
            errors.append({"row": index, "pair_id": pair_id, "path": "pair_id", "message": "duplicate review pair"})
        seen.add(pair_id)
        if not isinstance(row.get("notes"), str):
            errors.append({"row": index, "pair_id": pair_id, "path": "notes", "message": "notes must be a string"})
        for field, values in allowed.items():
            if row.get(field) not in values:
                errors.append({"row": index, "pair_id": pair_id, "path": field, "message": f"{field} has an invalid value"})
    missing = expected - seen
    if missing:
        errors.append({"row": None, "pair_id": None, "path": "pair_id", "message": f"missing {len(missing)} review pairs"})
    return errors


def assemble_llm_review_submission(
    response_paths: list[str | Path],
    review_dir: str | Path,
    output_path: str | Path,
    reviewer_id: str = "llm-reviewer",
) -> dict[str, Any]:
    """Assemble validated LLM chunk responses into one llm_reviewer submission JSONL."""
    root = Path(review_dir)
    packet_path = root / "reviewer_packet_blinded.jsonl"
    if not packet_path.exists():
        raise FileNotFoundError(f"{packet_path} does not exist")
    paths = [Path(path) for path in response_paths]
    if not paths:
        raise ValueError("at least one response file is required")
    expected_pair_ids = [str(row["pair_id"]) for row in load_jsonl(packet_path)]
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(load_jsonl(path))
    errors = _validate_llm_rows(rows, expected_pair_ids, reviewer_id)
    if errors:
        return {"valid": False, "n_errors": len(errors), "errors": errors, "output": str(output_path)}
    by_pair_id = {str(row["pair_id"]): row for row in rows}
    ordered = [by_pair_id[pair_id] for pair_id in expected_pair_ids]
    write_jsonl(output_path, ordered)
    return {
        "valid": True,
        "n_errors": 0,
        "errors": [],
        "output": str(output_path),
        "reviewer_slot": LLM_REVIEWER_SLOT,
        "reviewer_id": reviewer_id,
        "n_pairs": len(ordered),
        "response_files": [str(path) for path in paths],
    }
