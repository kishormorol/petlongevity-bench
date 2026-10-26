"""Provider-neutral B0/B1 runner with a deterministic offline adapter."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol, Sequence

from .io import load_json, load_jsonl, sha256_file, write_json, write_jsonl
from .schema import validate_records
from .temporal import audit_snapshot


RUN_MANIFEST_SCHEMA = Path(__file__).parents[2] / "schemas" / "run_manifest_schema.json"
EVIDENCE_SCHEMA = Path(__file__).parents[2] / "schemas" / "evidence_schema.json"
_ID_KEYS = {"M1": "record_id", "M2": "item_id", "M3": "candidate_id", "M4": "feature_id"}
_SENSITIVE_KEYS = {"api_key", "apikey", "authorization", "password", "secret", "token"}


@dataclass(frozen=True)
class AdapterResponse:
    """One prediction and its provider/raw-response representation."""

    request_id: str
    prediction: dict[str, Any]
    raw_response: str


class ModelAdapter(Protocol):
    """Provider boundary: adapters turn benchmark requests into prediction records."""

    model_name: str
    model_version: str

    def generate(self, requests: Sequence[dict[str, Any]], id_key: str) -> list[AdapterResponse]:
        """Generate one response for each request."""


class OfflineJsonlAdapter:
    """Deterministic adapter backed by a precomputed prediction JSONL file."""

    model_name = "offline-jsonl"
    model_version = "1"

    def __init__(self, predictions_path: str | Path) -> None:
        self.predictions_path = Path(predictions_path)

    def generate(self, requests: Sequence[dict[str, Any]], id_key: str) -> list[AdapterResponse]:
        predictions = load_jsonl(self.predictions_path)
        indexed: dict[str, dict[str, Any]] = {}
        for row in predictions:
            value = row.get(id_key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"offline prediction missing {id_key}")
            if value in indexed:
                raise ValueError(f"duplicate offline prediction {id_key}: {value}")
            indexed[value] = row
        request_ids = [row.get(id_key) for row in requests]
        if any(not isinstance(value, str) or not value for value in request_ids):
            raise ValueError(f"request missing {id_key}")
        missing = sorted(set(request_ids) - set(indexed))
        extra = sorted(set(indexed) - set(request_ids))
        if missing:
            raise ValueError(f"missing offline predictions for {id_key}: {', '.join(missing)}")
        if extra:
            raise ValueError(f"offline predictions do not match inputs for {id_key}: {', '.join(extra)}")
        return [AdapterResponse(value, indexed[value], json.dumps(indexed[value], ensure_ascii=False, sort_keys=True)) for value in request_ids]


def _has_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key).lower().replace("-", "_") in _SENSITIVE_KEYS or _has_sensitive_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_sensitive_key(item) for item in value)
    return False


def _hash_raw_responses(responses: Sequence[AdapterResponse]) -> str:
    digest = hashlib.sha256()
    for response in responses:
        digest.update(response.raw_response.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _validate_predictions(module: str, rows: Sequence[dict[str, Any]]) -> None:
    id_key = _ID_KEYS[module]
    if module == "M1":
        errors = validate_records(rows, EVIDENCE_SCHEMA)
        if errors:
            raise ValueError(f"invalid M1 prediction: {errors[0]['message']}")
        return
    for row in rows:
        if not isinstance(row.get(id_key), str) or not row[id_key]:
            raise ValueError(f"prediction missing {id_key}")
        if module == "M2" and row.get("label") not in {"supported", "contradicted", "insufficient"}:
            raise ValueError("M2 prediction label must be supported, contradicted, or insufficient")
        if module in {"M3", "M4"}:
            try:
                float(row["score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{module} prediction requires numeric score") from exc


def validate_run_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return schema errors for a generated run manifest."""
    return validate_records([manifest], RUN_MANIFEST_SCHEMA)


def run_offline(
    module: str,
    baseline: str,
    inputs_path: str | Path,
    responses_path: str | Path,
    predictions_path: str | Path,
    manifest_path: str | Path,
    response_cache_path: str | Path,
    prompt_path: str | Path,
    generation_settings: dict[str, Any] | None = None,
    snapshot_manifest_path: str | Path | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    run_date: str | None = None,
) -> dict[str, Any]:
    """Execute B0/B1 with offline predictions and write reproducible run artifacts."""
    module, baseline = module.upper(), baseline.upper()
    if module not in _ID_KEYS:
        raise ValueError("module must be M1, M2, M3, or M4")
    if baseline not in {"B0", "B1"}:
        raise ValueError("baseline must be B0 or B1")
    if baseline == "B1" and snapshot_manifest_path is None:
        raise ValueError("B1 requires a frozen snapshot manifest")
    if baseline == "B0" and snapshot_manifest_path is not None:
        raise ValueError("B0 must not receive retrieval snapshot context")
    settings = {} if generation_settings is None else generation_settings
    if not isinstance(settings, dict):
        raise ValueError("generation settings must be a JSON object")
    if _has_sensitive_key(settings):
        raise ValueError("generation settings must not contain secrets")
    snapshot: dict[str, Any] | None = None
    if snapshot_manifest_path is not None:
        audit = audit_snapshot(snapshot_manifest_path, strict=True, prompt_path=prompt_path)
        if not audit["leakage_free"]:
            raise ValueError("B1 snapshot failed strict leakage audit")
        snapshot = load_json(snapshot_manifest_path)
    inputs = load_jsonl(inputs_path)
    request_ids = [row.get(_ID_KEYS[module]) for row in inputs]
    if any(not isinstance(value, str) or not value for value in request_ids):
        raise ValueError(f"request missing {_ID_KEYS[module]}")
    if len(set(request_ids)) != len(request_ids):
        raise ValueError(f"inputs contain duplicate {_ID_KEYS[module]} values")
    adapter = OfflineJsonlAdapter(responses_path)
    responses = adapter.generate(inputs, _ID_KEYS[module])
    predictions = [response.prediction for response in responses]
    if any(_has_sensitive_key(response.prediction) for response in responses):
        raise ValueError("offline responses must not contain secrets")
    _validate_predictions(module, predictions)
    write_jsonl(predictions_path, predictions)
    cache_rows = [{"request_id": response.request_id, "raw_response": response.raw_response, "raw_response_sha256": hashlib.sha256(response.raw_response.encode("utf-8")).hexdigest()} for response in responses]
    write_jsonl(response_cache_path, cache_rows)
    manifest = {
        "benchmark_version": "0.3",
        "module": module,
        "baseline": baseline,
        "model_name": model_name or adapter.model_name,
        "model_version": model_version or adapter.model_version,
        "run_date": run_date or date.today().isoformat(),
        "prompt_hash": sha256_file(prompt_path),
        "corpus_snapshot_date": snapshot.get("retrieved_at") if snapshot else None,
        "candidate_universe_hash": sha256_file(inputs_path) if module == "M3" else None,
        "database_versions": {entry["name"]: entry["version"] for entry in snapshot.get("version_registry", [])} if snapshot else {},
        "internet_access": False,
        "post_cutoff_leakage_detected": False,
        "temporal_leakage_status": "leakage_free" if snapshot else "not_a_temporal_run",
        "closed_model_pretraining_risk": "not_applicable",
        "source_snapshot_hash": sha256_file(snapshot_manifest_path) if snapshot_manifest_path else None,
        "generation_settings": settings,
        "raw_response_sha256": _hash_raw_responses(responses),
        "prediction_sha256": sha256_file(predictions_path),
    }
    errors = validate_run_manifest(manifest)
    if errors:
        raise ValueError(f"invalid run manifest: {errors[0]['message']}")
    write_json(manifest_path, manifest)
    return manifest
