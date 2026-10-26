from pathlib import Path

import pytest

from petlongevity_bench.kg import SpeciesKnowledgeGraph, load_graph, validate_graph


BASE = Path(__file__).parents[1] / "data" / "demo"


def test_direct_feline_query_excludes_dog_only_evidence():
    graph = load_graph(BASE / "kg_nodes.jsonl", BASE / "kg_edges.jsonl")
    result = graph.retrieve("I:demo", species="cat", direct_species_evidence=True)
    assert [edge["edge_id"] for edge in result["edges"]] == ["E:cat"]


def test_temporal_filter_removes_post_cutoff_edge():
    nodes = [{"node_id": "I", "node_type": "intervention", "label": "I"}, {"node_id": "O", "node_type": "outcome", "label": "O"}]
    edges = [{"edge_id": "future", "subject_id": "I", "predicate": "associated_with", "object_id": "O", "evidence": True, "species": ["cat"], "source_id": "TEST:1", "source_date": "2021-01-01", "evidence_level": "T2", "provenance_url": "https://example.org/1"}]
    assert SpeciesKnowledgeGraph(nodes, edges).retrieve("I", cutoff="2020-12-31")["edges"] == []


def test_graph_rejects_evidence_missing_provenance():
    nodes = [{"node_id": "I", "node_type": "intervention", "label": "I"}, {"node_id": "O", "node_type": "outcome", "label": "O"}]
    edges = [{"edge_id": "bad", "subject_id": "I", "predicate": "associated_with", "object_id": "O", "evidence": True, "species": ["dog"], "source_id": "TEST:2", "source_date": "2020-01-01", "evidence_level": "T2"}]
    assert validate_graph(nodes, edges)
    with pytest.raises(ValueError, match="invalid knowledge graph"):
        SpeciesKnowledgeGraph(nodes, edges)
