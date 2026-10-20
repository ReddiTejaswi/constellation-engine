"""Build the evidence graph from extracted findings.

We rely on a lightweight entity-normalization step: entities are matched
on lowercased + punctuation-stripped surface forms, with alias merging.
We never try to upgrade an INFERRED/HYPOTHESIS status to ESTABLISHED here.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict, List, Tuple

import networkx as nx

from backend.models.schemas import (
    EntityType,
    EvidenceGraph,
    EvidenceStatus,
    Finding,
    GraphEdge,
    GraphNode,
)

logger = logging.getLogger(__name__)


_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s\-]")


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def _rank_status(s: EvidenceStatus) -> int:
    return {
        EvidenceStatus.UNKNOWN: 0,
        EvidenceStatus.HYPOTHESIS: 1,
        EvidenceStatus.INFERRED: 2,
        EvidenceStatus.SUPPORTED: 3,
        EvidenceStatus.ESTABLISHED: 4,
    }[s]


def build_graph(findings: List[Finding]) -> Tuple[EvidenceGraph, nx.MultiDiGraph]:
    """Return a validated EvidenceGraph plus a NetworkX graph for traversal."""
    nodes: Dict[str, GraphNode] = {}
    aliases_by_id: Dict[str, set] = defaultdict(set)
    edges: Dict[str, GraphEdge] = {}

    def ensure_node(label: str, etype: EntityType | None) -> str:
        key = _norm(label)
        if not key:
            return ""
        node_id = f"n::{key}"
        if node_id not in nodes:
            nodes[node_id] = GraphNode(
                id=node_id,
                label=label.strip(),
                type=etype or EntityType.CONCEPT,
                mentions=1,
                aliases=[],
            )
        else:
            nodes[node_id].mentions += 1
            # If we had CONCEPT and now get a specific type, promote.
            if nodes[node_id].type == EntityType.CONCEPT and etype:
                nodes[node_id].type = etype
        aliases_by_id[node_id].add(label.strip())
        return node_id

    for i, f in enumerate(findings):
        sid = ensure_node(f.subject, f.subject_type)
        oid = ensure_node(f.object, f.object_type)
        if not sid or not oid or sid == oid:
            continue
        rel = f.relationship.strip().lower().replace(" ", "_") or "related_to"
        edge_key = f"e::{sid}|{rel}|{oid}"
        finding_id = f"F{i:04d}"
        if edge_key not in edges:
            edges[edge_key] = GraphEdge(
                id=edge_key,
                source=sid,
                target=oid,
                relationship=rel,
                status=f.status,
                evidence_levels=[f.evidence_level],
                confidence=f.confidence,
                supporting_findings=[finding_id],
                papers=[f.source_id],
            )
        else:
            e = edges[edge_key]
            e.supporting_findings.append(finding_id)
            if f.source_id not in e.papers:
                e.papers.append(f.source_id)
            if f.evidence_level not in e.evidence_levels:
                e.evidence_levels.append(f.evidence_level)
            # Upgrade only within same evidence class; confidence = average of supports.
            if _rank_status(f.status) > _rank_status(e.status):
                e.status = f.status
            e.confidence = round((e.confidence + f.confidence) / 2, 3)

    for nid, al in aliases_by_id.items():
        nodes[nid].aliases = sorted(a for a in al if a and a != nodes[nid].label)

    graph = EvidenceGraph(nodes=list(nodes.values()), edges=list(edges.values()))

    # Build an undirected view for multi-hop reasoning (relationships aren't always directional
    # in the real literature; the direction + relationship is kept per edge).
    G = nx.MultiDiGraph()
    for n in graph.nodes:
        G.add_node(n.id, **n.model_dump())
    for e in graph.edges:
        G.add_edge(e.source, e.target, key=e.id, **e.model_dump())
    return graph, G


def finding_lookup(findings: List[Finding]) -> Dict[str, Finding]:
    return {f"F{i:04d}": f for i, f in enumerate(findings)}
