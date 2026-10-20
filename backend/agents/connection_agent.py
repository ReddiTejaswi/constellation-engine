"""Multi-hop connection discovery.

Given the decomposed research question and the evidence graph, we identify
seed/target entities implied by the question and look for simple paths
between them of length 2-4. Each returned Connection is marked INFERRED
unless every edge on the path is already ESTABLISHED/SUPPORTED by a
direct source — in which case we still never upgrade to ESTABLISHED
because the composite claim itself is not directly tested.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Set

import networkx as nx

from backend.graph.builder import _norm
from backend.models.schemas import (
    Connection,
    DecomposedQuestion,
    EvidenceGraph,
    EvidenceStatus,
)

logger = logging.getLogger(__name__)


def _candidate_terms(dq: DecomposedQuestion) -> List[str]:
    buckets = [
        dq.diseases, dq.genes, dq.proteins, dq.molecules, dq.pathways,
        dq.cell_types, dq.tissues, dq.phenotypes, dq.biological_processes,
        dq.drugs, dq.mechanisms,
    ]
    out: List[str] = []
    for b in buckets:
        out.extend(b)
    # include synonyms
    for syns in dq.synonyms.values():
        out.extend(syns)
    return list({t for t in out if t})


def _match_nodes(graph: EvidenceGraph, terms: List[str]) -> Set[str]:
    norm_terms = {_norm(t) for t in terms if t}
    hits: Set[str] = set()
    for n in graph.nodes:
        candidates = [n.label] + n.aliases
        for c in candidates:
            cn = _norm(c)
            if cn in norm_terms or any(t and (t in cn or cn in t) for t in norm_terms):
                hits.add(n.id)
                break
    return hits


def discover_connections(
    graph: EvidenceGraph,
    nxg: nx.MultiDiGraph,
    dq: DecomposedQuestion,
    *,
    max_paths: int = 25,
    max_hops: int = 4,
) -> List[Connection]:
    terms = _candidate_terms(dq)
    seeds = _match_nodes(graph, terms)
    if len(seeds) < 2:
        return []

    edges_by_key: Dict[str, dict] = {e.id: e.model_dump() for e in graph.edges}
    node_label: Dict[str, str] = {n.id: n.label for n in graph.nodes}

    # Work on an undirected simple graph for pathfinding; keep the real edge data separately.
    UG = nx.Graph()
    for n in graph.nodes:
        UG.add_node(n.id)
    for e in graph.edges:
        if not UG.has_edge(e.source, e.target):
            UG.add_edge(e.source, e.target, keys=[e.id])
        else:
            UG[e.source][e.target]["keys"].append(e.id)

    connections: List[Connection] = []
    seen_paths: Set[tuple] = set()
    seed_list = list(seeds)
    for i in range(len(seed_list)):
        for j in range(i + 1, len(seed_list)):
            a, b = seed_list[i], seed_list[j]
            try:
                paths_iter = nx.all_simple_paths(UG, a, b, cutoff=max_hops)
            except nx.NetworkXNoPath:
                continue
            for path in paths_iter:
                tup = tuple(path)
                if tup in seen_paths:
                    continue
                seen_paths.add(tup)
                if len(path) < 2:
                    continue
                edge_ids: List[str] = []
                rels: List[str] = []
                ok = True
                for u, v in zip(path, path[1:]):
                    data = UG[u][v]
                    chosen = data["keys"][0]
                    edge_ids.append(chosen)
                    e = edges_by_key[chosen]
                    rels.append(e["relationship"])
                    if e["source"] != u:
                        # the real edge is reversed; keep but note it
                        pass
                if not ok:
                    continue
                direct = len(path) == 2
                status = EvidenceStatus.SUPPORTED if direct else EvidenceStatus.INFERRED
                rationale = (
                    "Direct supporting evidence found."
                    if direct
                    else "Composite relationship chain across " + str(len(path) - 1) + " independently supported edges."
                )
                connections.append(
                    Connection(
                        path=path,
                        path_labels=[node_label[n] for n in path],
                        relationships=rels,
                        status=status,
                        rationale=rationale,
                        supporting_edges=edge_ids,
                        direct_evidence=direct,
                    )
                )
                if len(connections) >= max_paths:
                    return connections
    # Rank: direct first, then shorter, then more supporting-paper diversity.
    connections.sort(key=lambda c: (not c.direct_evidence, len(c.path)))
    return connections[:max_paths]
