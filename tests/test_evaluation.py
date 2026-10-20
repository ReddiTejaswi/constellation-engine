from backend.evaluation.metrics import (
    citation_accuracy, graph_integrity, connection_integrity,
)
from backend.graph.builder import build_graph
from backend.models.schemas import (
    DiscoveryReport, DecomposedQuestion, EntityType, EvidenceLevel,
    EvidenceStatus, Finding, Paper,
)


def _paper(pid, abstract):
    return Paper(identifier=pid, title=f"T{pid}", source="pubmed", abstract=abstract)


def test_citation_accuracy_matches_quotes_in_abstracts():
    papers = [_paper("PMID:1", "Protein X activates Pathway Y in neurons.")]
    findings = [
        Finding(
            subject="Protein X", subject_type=EntityType.PROTEIN,
            relationship="activates", object="Pathway Y",
            object_type=EntityType.PATHWAY,
            evidence_level=EvidenceLevel.CELL_CULTURE,
            source_id="PMID:1", source_quote="Protein X activates Pathway Y in neurons.",
            status=EvidenceStatus.SUPPORTED,
        ),
    ]
    acc = citation_accuracy(findings, papers)
    assert acc["cited_ok"] == 1
    assert acc["cited_bad"] == 0


def test_graph_integrity_detects_no_orphans():
    f = Finding(
        subject="A", relationship="regulates", object="B",
        source_id="PMID:1", status=EvidenceStatus.SUPPORTED,
    )
    graph, _ = build_graph([f])
    report = DiscoveryReport(
        research_question="?",
        decomposition=DecomposedQuestion(original_question="?"),
        papers=[], findings=[f], graph=graph, key_findings=[],
        connections=[], contradictions=[], gaps=[], hypotheses=[],
    )
    integ = graph_integrity(report)
    assert integ["orphan_edges"] == []
