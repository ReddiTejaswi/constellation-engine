"""Research-gap detection.

For every inferred multi-hop connection, flag the specific pair of entities
whose direct relationship was NOT found in the retrieved literature.
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

from backend.models.schemas import Connection, EvidenceGraph, ResearchGap


def detect_gaps(graph: EvidenceGraph, connections: List[Connection]) -> List[ResearchGap]:
    direct_pairs: Set[Tuple[str, str]] = set()
    for e in graph.edges:
        direct_pairs.add(tuple(sorted([e.source, e.target])))

    labels: Dict[str, str] = {n.id: n.label for n in graph.nodes}
    gaps: List[ResearchGap] = []
    seen_gap: Set[Tuple[str, str]] = set()
    for c in connections:
        if c.direct_evidence:
            continue
        if len(c.path) < 2:
            continue
        a, b = c.path[0], c.path[-1]
        key = tuple(sorted([a, b]))
        if key in seen_gap:
            continue
        if key in direct_pairs:
            continue
        seen_gap.add(key)
        gaps.append(
            ResearchGap(
                description=(
                    f"No direct study was identified in the searched sources linking "
                    f"'{labels.get(a, a)}' with '{labels.get(b, b)}'. "
                    f"Supporting intermediate findings exist across {len(c.path) - 1} hops."
                ),
                missing_edge={"source": a, "target": b, "relationship": "direct_relationship"},
                adjacent_evidence=c.supporting_edges,
                rationale=(
                    "Each intermediate edge of the discovered connection is supported by at least "
                    "one source, but the end-to-end relationship itself has no direct supporting study "
                    "in the retrieved literature."
                ),
            )
        )
    return gaps
