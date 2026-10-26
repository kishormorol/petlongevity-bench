"""Small, provider-neutral in-memory reference implementation for species-aware evidence graphs."""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Sequence

from .io import load_jsonl, write_jsonl
from .leakage import _d
from .schema import validate_records


NODE_SCHEMA = Path(__file__).parents[2] / "schemas" / "kg_node_schema.json"
EDGE_SCHEMA = Path(__file__).parents[2] / "schemas" / "kg_edge_schema.json"


class SpeciesKnowledgeGraph:
    """Validated graph that returns only provenance-bearing, species-compatible evidence."""

    def __init__(self, nodes: Sequence[dict[str, Any]], edges: Sequence[dict[str, Any]]) -> None:
        errors = validate_graph(nodes, edges)
        if errors:
            raise ValueError(f"invalid knowledge graph: {errors[0]['message']}")
        self.nodes = {node["node_id"]: node for node in nodes}
        self.edges = list(edges)

    def retrieve(
        self,
        node_id: str,
        species: str | None = None,
        direct_species_evidence: bool = False,
        cutoff: str | None = None,
        max_hops: int = 1,
    ) -> dict[str, Any]:
        """Return a bounded neighborhood with date- and species-compatible evidence edges."""
        if node_id not in self.nodes:
            raise ValueError(f"unknown node_id: {node_id}")
        if species not in {None, "dog", "cat", "human", "mouse", "rat", "other"}:
            raise ValueError("unknown species")
        if max_hops < 1:
            raise ValueError("max_hops must be at least 1")
        cutoff_date = _d(cutoff) if cutoff else None
        frontier = deque([(node_id, 0)])
        visited = {node_id}
        selected: list[dict[str, Any]] = []
        while frontier:
            current, depth = frontier.popleft()
            if depth >= max_hops:
                continue
            for edge in self.edges:
                if current not in {edge["subject_id"], edge["object_id"]} or not self._eligible(edge, species, direct_species_evidence, cutoff_date):
                    continue
                selected.append(edge)
                neighbor = edge["object_id"] if edge["subject_id"] == current else edge["subject_id"]
                if neighbor not in visited:
                    visited.add(neighbor)
                    frontier.append((neighbor, depth + 1))
        return {"node_id": node_id, "species": species, "direct_species_evidence": direct_species_evidence, "cutoff": cutoff, "nodes": [self.nodes[key] for key in sorted(visited)], "edges": selected}

    @staticmethod
    def _eligible(edge: dict[str, Any], species: str | None, direct: bool, cutoff: Any) -> bool:
        if not edge["evidence"]:
            return False
        if not edge.get("provenance_url"):
            return False
        try:
            if cutoff and _d(edge["source_date"]) > cutoff:
                return False
        except (KeyError, TypeError, ValueError):
            return False
        if species and direct and species not in edge.get("species", []):
            return False
        return True


def validate_graph(nodes: Sequence[dict[str, Any]], edges: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return schema and reference-integrity errors for JSONL graph records."""
    errors = validate_records(nodes, NODE_SCHEMA) + validate_records(edges, EDGE_SCHEMA)
    node_ids = [node.get("node_id") for node in nodes]
    if len(set(node_ids)) != len(node_ids):
        errors.append({"row": None, "record_id": None, "path": "nodes", "message": "duplicate node_id"})
    known = set(node_ids)
    edge_ids = [edge.get("edge_id") for edge in edges]
    if len(set(edge_ids)) != len(edge_ids):
        errors.append({"row": None, "record_id": None, "path": "edges", "message": "duplicate edge_id"})
    for row, edge in enumerate(edges):
        for key in ("subject_id", "object_id"):
            if edge.get(key) not in known:
                errors.append({"row": row, "record_id": edge.get("edge_id"), "path": key, "message": "edge references an unknown node"})
    return errors


def load_graph(nodes_path: str | Path, edges_path: str | Path) -> SpeciesKnowledgeGraph:
    """Load a JSONL node/edge graph into the in-memory reference implementation."""
    return SpeciesKnowledgeGraph(load_jsonl(nodes_path), load_jsonl(edges_path))


def export_graph(graph: SpeciesKnowledgeGraph, nodes_path: str | Path, edges_path: str | Path) -> None:
    """Export graph records as deterministic JSONL files."""
    write_jsonl(nodes_path, graph.nodes.values())
    write_jsonl(edges_path, graph.edges)
