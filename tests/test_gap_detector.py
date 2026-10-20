from backend.agents.gap_detector import detect_gaps
from backend.agents.connection_agent import discover_connections
from backend.graph.builder import build_graph
from backend.models.schemas import (
    DecomposedQuestion, EntityType, EvidenceLevel, EvidenceStatus, Finding,
)


def _f(s, r, o, src):
    return Finding(
        subject=s, subject_type=EntityType.PROTEIN, relationship=r, object=o,
        object_type=EntityType.PATHWAY, evidence_level=EvidenceLevel.CELL_CULTURE,
        source_id=src, status=EvidenceStatus.SUPPORTED,
    )


def test_gap_detected_only_between_endpoints_not_directly_connected():
    findings = [
        _f("Protein X", "regulates", "Pathway Y", "PMID:1"),
        _f("Pathway Y", "affects", "Cell Z", "PMID:2"),
        _f("Cell Z", "reduced_in", "Disease D", "PMID:3"),
    ]
    graph, nxg = build_graph(findings)
    dq = DecomposedQuestion(
        original_question="Protein X and Disease D?",
        proteins=["Protein X"], diseases=["Disease D"],
    )
    conns = discover_connections(graph, nxg, dq)
    gaps = detect_gaps(graph, conns)
    assert gaps, "expected at least one gap"
    assert any("Protein X" in g.description and "Disease D" in g.description for g in gaps)
