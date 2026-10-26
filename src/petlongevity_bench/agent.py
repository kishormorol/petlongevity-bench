"""Agent-neutral, offline B3 orchestration with evidence verification and sanitized traces."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol, Sequence

from .io import load_json, load_jsonl, sha256_file, write_json, write_jsonl
from .kg import load_graph
from .runner import _has_sensitive_key, _validate_predictions, validate_run_manifest
from .schema import validate_records
from .temporal import audit_snapshot


AGENT_RESPONSE_SCHEMA = Path(__file__).parents[2] / "schemas" / "agent_response_schema.json"
TOOL_TRACE_SCHEMA = Path(__file__).parents[2] / "schemas" / "tool_trace_schema.json"
_ID_KEYS = {"M1": "record_id", "M2": "item_id", "M3": "candidate_id", "M4": "feature_id"}
_SECRET_TEXT = re.compile(r"(?i)(api[_-]?key|token|authorization|password|secret)\s*[:=]\s*\S+")


@dataclass(frozen=True)
class ToolResult:
    """A deterministic tool result containing only evidence identifiers and metadata."""

    tool_name: str
    evidence_ids: list[str]


class ScientificTool(Protocol):
    """Agent-neutral deterministic-tool contract."""

    name: str

    def execute(self) -> ToolResult:
        """Return grounded evidence identifiers or raise a visible failure."""


class SnapshotRetrievalTool:
    name = "snapshot_retrieval"

    def __init__(self, snapshot_manifest_path: str | Path, prompt_path: str | Path) -> None:
        self.snapshot_manifest_path = Path(snapshot_manifest_path)
        self.prompt_path = Path(prompt_path)

    def execute(self) -> ToolResult:
        audit = audit_snapshot(self.snapshot_manifest_path, strict=True, prompt_path=self.prompt_path)
        if not audit["leakage_free"]:
            raise ValueError("snapshot retrieval blocked by strict leakage audit")
        manifest = load_json(self.snapshot_manifest_path)
        records = load_jsonl(self.snapshot_manifest_path.parent / manifest["records_file"])
        return ToolResult(self.name, [record["source_id"] for record in records])


class SpeciesKnowledgeGraphTool:
    name = "species_knowledge_graph"

    def __init__(self, nodes_path: str | Path, edges_path: str | Path, node_id: str, species: str | None, cutoff: str | None) -> None:
        self.nodes_path, self.edges_path = Path(nodes_path), Path(edges_path)
        self.node_id, self.species, self.cutoff = node_id, species, cutoff

    def execute(self) -> ToolResult:
        result = load_graph(self.nodes_path, self.edges_path).retrieve(self.node_id, self.species, bool(self.species), self.cutoff)
        ids = [edge["edge_id"] for edge in result["edges"]] + [edge["source_id"] for edge in result["edges"] if edge.get("evidence")]
        return ToolResult(self.name, ids)


def verify_claims(claims: Sequence[dict[str, Any]], evidence_ids: set[str]) -> list[dict[str, Any]]:
    """Return verification failures; supported claims must cite available evidence."""
    failures: list[dict[str, Any]] = []
    for claim in claims:
        cited = set(claim.get("evidence_ids", []))
        if claim.get("status") == "supported" and not cited:
            failures.append({"claim_id": claim.get("claim_id"), "reason": "supported_claim_missing_evidence"})
        elif claim.get("status") == "supported" and not cited <= evidence_ids:
            failures.append({"claim_id": claim.get("claim_id"), "reason": "claim_cites_unavailable_evidence"})
    return failures


def _trace(tool_name: str, status: str, evidence_ids: Sequence[str] = (), error: str | None = None) -> dict[str, Any]:
    sanitized_error = _SECRET_TEXT.sub(lambda match: f"{match.group(1)}=[REDACTED]", error) if error else None
    return {"tool_name": tool_name, "status": status, "evidence_ids": list(evidence_ids), "error": sanitized_error}


def run_b3_offline(
    module: str,
    inputs_path: str | Path,
    responses_path: str | Path,
    predictions_path: str | Path,
    manifest_path: str | Path,
    trace_path: str | Path,
    prompt_path: str | Path,
    snapshot_manifest_path: str | Path,
    kg_nodes_path: str | Path,
    kg_edges_path: str | Path,
    kg_node_id: str,
    species: str | None = None,
    tools: Sequence[ScientificTool] | None = None,
    run_date: str | None = None,
) -> dict[str, Any]:
    """Run offline B3 envelopes; unsupported claims and failed tools cannot be hidden."""
    module = module.upper()
    if module not in _ID_KEYS:
        raise ValueError("module must be M1, M2, M3, or M4")
    manifest_snapshot = load_json(snapshot_manifest_path)
    default_tools: Sequence[ScientificTool] = [
        SnapshotRetrievalTool(snapshot_manifest_path, prompt_path),
        SpeciesKnowledgeGraphTool(kg_nodes_path, kg_edges_path, kg_node_id, species, manifest_snapshot.get("effective_cutoff")),
    ]
    traces: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()
    failed = False
    for tool in tools or default_tools:
        try:
            result = tool.execute()
            evidence_ids.update(result.evidence_ids)
            traces.append(_trace(result.tool_name, "success", result.evidence_ids))
        except Exception as exc:
            failed = True
            traces.append(_trace(getattr(tool, "name", type(tool).__name__), "failure", error=str(exc)))
    if any(_has_sensitive_key(trace) for trace in traces):
        raise ValueError("tool traces must not contain secrets")
    trace_errors = validate_records(traces, TOOL_TRACE_SCHEMA)
    if trace_errors:
        raise ValueError(f"invalid tool trace: {trace_errors[0]['message']}")
    write_jsonl(trace_path, traces)
    inputs, envelopes = load_jsonl(inputs_path), load_jsonl(responses_path)
    if any(_has_sensitive_key(envelope) for envelope in envelopes):
        raise ValueError("agent responses must not contain secrets")
    response_errors = validate_records(envelopes, AGENT_RESPONSE_SCHEMA)
    if response_errors:
        raise ValueError(f"invalid agent response: {response_errors[0]['message']}")
    key = _ID_KEYS[module]
    by_id = {row["request_id"]: row for row in envelopes}
    request_ids = [row.get(key) for row in inputs]
    if any(not isinstance(value, str) for value in request_ids) or set(request_ids) != set(by_id) or len(request_ids) != len(by_id):
        raise ValueError("agent responses must exactly match input request identifiers")
    claims = [claim for row in envelopes for claim in row["claims"]]
    verification_failures = verify_claims(claims, evidence_ids)
    if failed and any(claim["status"] == "supported" for claim in claims):
        verification_failures.insert(0, {"claim_id": None, "reason": "tool_failure_requires_uncertainty"})
    if verification_failures:
        write_json(Path(str(trace_path) + ".verification.json"), {"valid": False, "failures": verification_failures})
        raise ValueError(f"claim verification failed: {verification_failures[0]['reason']}")
    predictions = [by_id[request_id]["prediction"] for request_id in request_ids]
    _validate_predictions(module, predictions)
    write_jsonl(predictions_path, predictions)
    run_manifest = {
        "benchmark_version": "0.3", "module": module, "baseline": "B3",
        "model_name": "offline-b3-agent", "model_version": "1", "run_date": run_date or date.today().isoformat(),
        "prompt_hash": sha256_file(prompt_path), "corpus_snapshot_date": manifest_snapshot.get("retrieved_at"),
        "candidate_universe_hash": sha256_file(inputs_path) if module == "M3" else None,
        "database_versions": {entry["name"]: entry["version"] for entry in manifest_snapshot.get("version_registry", [])},
        "internet_access": False, "post_cutoff_leakage_detected": False, "temporal_leakage_status": "leakage_free",
        "closed_model_pretraining_risk": "not_applicable", "source_snapshot_hash": sha256_file(snapshot_manifest_path),
        "generation_settings": {}, "raw_response_sha256": hashlib.sha256("".join(json.dumps(row, sort_keys=True) for row in envelopes).encode("utf-8")).hexdigest(),
        "prediction_sha256": sha256_file(predictions_path),
    }
    errors = validate_run_manifest(run_manifest)
    if errors:
        raise ValueError(f"invalid B3 run manifest: {errors[0]['message']}")
    write_json(manifest_path, run_manifest)
    return {"manifest": run_manifest, "tool_trace": traces, "evidence_ids": sorted(evidence_ids)}
