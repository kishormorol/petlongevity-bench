"""Deterministic manifests and strict audits for historical evidence snapshots."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from .io import load_json, load_jsonl, sha256_file, write_json
from .leakage import _d, audit_sources
from .schema import validate_records


SNAPSHOT_MANIFEST_SCHEMA = Path(__file__).parents[2] / "schemas" / "temporal_snapshot_manifest_schema.json"
_DATE_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}-\d{2}-\d{2}(?!\d)")


def content_sha256(records: Sequence[dict[str, Any]]) -> str:
    """Hash records canonically, preserving their frozen order."""
    digest = hashlib.sha256()
    for record in records:
        digest.update(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def freeze_snapshot(
    records_path: str | Path,
    manifest_path: str | Path,
    snapshot_id: str,
    source: str,
    retrieval_query: str,
    effective_cutoff: str,
    version_registry: Sequence[dict[str, Any]],
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Write a manifest that freezes a JSONL corpus and its version metadata."""
    records_file, output = Path(records_path), Path(manifest_path)
    records = load_jsonl(records_file)
    manifest = {
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "source": source,
        "retrieval_query": retrieval_query,
        "retrieved_at": retrieved_at or date.today().isoformat(),
        "effective_cutoff": str(_d(effective_cutoff)),
        "records_file": os.path.relpath(records_file, output.parent),
        "records_sha256": sha256_file(records_file),
        "records_content_sha256": content_sha256(records),
        "record_count": len(records),
        "version_registry": list(version_registry),
    }
    write_json(output, manifest)
    return manifest


def audit_prompt(prompt_path: str | Path, cutoff: str, post_cutoff_source_ids: Sequence[str] = ()) -> list[dict[str, str]]:
    """Report explicit post-cutoff dates and known post-cutoff source anchors in a prompt."""
    c = _d(cutoff)
    text = Path(prompt_path).read_text(encoding="utf-8")
    issues = [
        {"kind": "post_cutoff_prompt_date", "date": value, "severity": "error"}
        for value in sorted(set(_DATE_RE.findall(text))) if _d(value) > c
    ]
    for source_id in sorted(set(post_cutoff_source_ids)):
        if source_id in text:
            issues.append({"kind": "post_cutoff_prompt_source_anchor", "source_id": source_id, "severity": "error"})
    return issues


def audit_snapshot(manifest_path: str | Path, strict: bool = True, prompt_path: str | Path | None = None) -> dict[str, Any]:
    """Audit a frozen corpus; strict mode fails post-cutoff, undated, or unprovenanced sources."""
    manifest_file = Path(manifest_path)
    manifest = load_json(manifest_file)
    schema_errors = validate_records([manifest], SNAPSHOT_MANIFEST_SCHEMA)
    records_path = manifest_file.parent / manifest.get("records_file", "")
    try:
        records = load_jsonl(records_path)
    except (OSError, ValueError) as exc:
        return {"strict": strict, "leakage_free": False, "issues": [{"kind": "records_unavailable", "severity": "error", "message": str(exc)}]}
    cutoff_value = manifest.get("effective_cutoff", "")
    try:
        cutoff = _d(cutoff_value)
    except (TypeError, ValueError):
        cutoff = None
    report = audit_sources(records, str(cutoff or date(9999, 12, 31)), strict=strict)
    issues: list[dict[str, Any]] = list(report["issues"])
    for error in schema_errors:
        issues.append({"kind": "invalid_manifest", "severity": "error", "path": error["path"], "message": error["message"]})
    if cutoff is None:
        issues.append({"kind": "invalid_cutoff", "severity": "error"})
    if manifest.get("record_count") != len(records):
        issues.append({"kind": "record_count_mismatch", "severity": "error"})
    expected_hash = manifest.get("records_sha256")
    if expected_hash != sha256_file(records_path):
        issues.append({"kind": "records_hash_mismatch", "severity": "error"})
    if manifest.get("records_content_sha256") != content_sha256(records):
        issues.append({"kind": "records_content_hash_mismatch", "severity": "error"})
    for version in manifest.get("version_registry", []):
        try:
            if cutoff and _d(version["effective_date"]) > cutoff:
                issues.append({"kind": "post_cutoff_version", "severity": "error", "name": version.get("name")})
        except (KeyError, TypeError, ValueError):
            issues.append({"kind": "invalid_version_date", "severity": "error", "name": version.get("name")})
    if prompt_path and cutoff:
        issues.extend(audit_prompt(prompt_path, str(cutoff), [leak["source_id"] for leak in report["leaks"]]))
    failed = any(issue["severity"] == "error" for issue in issues)
    return {
        "snapshot_id": manifest.get("snapshot_id"), "cutoff": manifest.get("effective_cutoff"),
        "strict": strict, "record_count": len(records), "records_sha256": expected_hash,
        "records_content_sha256": manifest.get("records_content_sha256"),
        "post_cutoff_leakage_detected": report["post_cutoff_leakage_detected"],
        "issues": issues, "leakage_free": not failed,
    }
