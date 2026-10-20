from backend.agents.connection_agent import discover_connections
from backend.graph.builder import build_graph
from backend.models.schemas import (
    DecomposedQuestion, EntityType, EvidenceLevel, EvidenceStatus, Finding,
)


def _f(s, r, o, src):
    return Finding(
        subject=s, subject_type=EntityType.PROTEIN, relationship=r,
        object=o, object_type=EntityType.PATHWAY,
        evidence_level=EvidenceLevel.CELL_CULTURE, source_id=src,
        status=EvidenceStatus.SUPPORTED,
    )


def test_multi_hop_inferred_connection_between_seeds():
    findings = [
        _f("Protein X", "regulates", "Pathway Y", "PMID:1"),
        _f("Pathway Y", "regulates_survival_of", "Neuron Z", "PMID:2"),
        _f("Neuron Z", "reduced_in", "Disease D", "PMID:3"),
    ]
    graph, nxg = build_graph(findings)
    dq = DecomposedQuestion(
        original_question="Could Protein X influence Disease D?",
        proteins=["Protein X"], diseases=["Disease D"],
    )
    conns = discover_connections(graph, nxg, dq)
    assert conns, "expected at least one connection"
    # path should go X -> Y -> Z -> D
    labels = [c.path_labels for c in conns]
    assert any("Protein X" in p and "Disease D" in p for p in labels)
    # since there is no direct edge X->D, this must be INFERRED
    for c in conns:
        if "Protein X" in c.path_labels and "Disease D" in c.path_labels:
            assert c.status == EvidenceStatus.INFERRED
            assert not c.direct_evidence
