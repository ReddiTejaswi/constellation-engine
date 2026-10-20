from backend.graph.builder import build_graph
from backend.models.schemas import (
    EntityType, EvidenceLevel, EvidenceStatus, Finding,
)


def _f(subj, rel, obj, src, status=EvidenceStatus.SUPPORTED, lvl=EvidenceLevel.CELL_CULTURE):
    return Finding(
        subject=subj, subject_type=EntityType.PROTEIN,
        relationship=rel,
        object=obj, object_type=EntityType.PATHWAY,
        evidence_level=lvl, source_id=src, status=status,
    )


def test_build_graph_merges_duplicates_and_tracks_provenance():
    findings = [
        _f("Protein X", "increases_activity_of", "Pathway Y", "PMID:1"),
        _f("protein x", "increases_activity_of", "pathway y", "PMID:2"),
        _f("Pathway Y", "regulates", "Cell Z", "PMID:3"),
    ]
    graph, nxg = build_graph(findings)
    labels = {n.id: n.label for n in graph.nodes}
    assert len(graph.nodes) == 3  # X, Y, Z

    xy = [e for e in graph.edges if "protein x" in labels[e.source].lower()][0]
    assert set(xy.papers) == {"PMID:1", "PMID:2"}
    assert len(xy.supporting_findings) == 2


def test_build_graph_never_upgrades_hypothesis_to_established():
    findings = [
        _f("A", "regulates", "B", "PMID:1", status=EvidenceStatus.HYPOTHESIS),
        _f("A", "regulates", "B", "PMID:2", status=EvidenceStatus.SUPPORTED),
    ]
    graph, _ = build_graph(findings)
    e = graph.edges[0]
    # Should rise to SUPPORTED (highest observed) but never to ESTABLISHED on its own.
    assert e.status == EvidenceStatus.SUPPORTED
