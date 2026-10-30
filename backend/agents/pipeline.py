"""End-to-end agentic pipeline.

Each stage is implemented as its own function; the orchestrator wires
them together, emits progress events for the UI, and composes the final
DiscoveryReport.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional

from backend.agents.connection_agent import discover_connections
from backend.agents.contradiction_agent import detect_contradictions
from backend.agents.evidence_extractor import extract_findings
from backend.agents.gap_detector import detect_gaps
from backend.agents.hypothesis_critic import critique_hypotheses
from backend.agents.hypothesis_generator import generate_hypotheses
from backend.agents.question_decomposer import decompose
from backend.agents.research_answer import generate_research_answer
from backend.graph.builder import build_graph, finding_lookup
from backend.models.llm import LLMClient
from backend.models.schemas import (
    DiscoveryReport,
    EvidenceStatus,
    Paper,
    ResearchAnswer,
)
from backend.retrieval import multi_search, build_providers

logger = logging.getLogger(__name__)


STAGES = [
    "decomposition",
    "retrieval",
    "extraction",
    "answer",
    "graph",
    "connections",
    "contradictions",
    "gaps",
    "hypotheses",
    "critique",
    "report",
]


@dataclass
class ProgressEvent:
    stage: str
    status: str  # started | completed | error
    message: str = ""
    data: Dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


async def run_pipeline(
    question: str,
    *,
    providers: Optional[List[str]] = None,
    year_cutoff: Optional[int] = None,
    max_results_per_provider: Optional[int] = None,
    llm: Optional[LLMClient] = None,
) -> DiscoveryReport:
    events: List[ProgressEvent] = []
    async for e in stream_pipeline(
        question,
        providers=providers,
        year_cutoff=year_cutoff,
        max_results_per_provider=max_results_per_provider,
        llm=llm,
    ):
        events.append(e)
    for e in reversed(events):
        if e.stage == "report" and e.status == "completed":
            return DiscoveryReport.model_validate(e.data["report"])
    raise RuntimeError("Pipeline did not produce a report.")


async def stream_pipeline(
    question: str,
    *,
    providers: Optional[List[str]] = None,
    year_cutoff: Optional[int] = None,
    max_results_per_provider: Optional[int] = None,
    llm: Optional[LLMClient] = None,
) -> AsyncIterator[ProgressEvent]:
    llm = llm or LLMClient()
    telemetry: Dict[str, float] = {}

    def ev(stage: str, status: str, msg: str = "", data=None) -> ProgressEvent:
        return ProgressEvent(stage=stage, status=status, message=msg, data=data or {})

    # 1. decomposition
    t0 = time.time()
    yield ev("decomposition", "started", f"Decomposing question into scientific concepts.")
    dq = await decompose(question, llm=llm)
    telemetry["decomposition_s"] = time.time() - t0
    yield ev("decomposition", "completed", f"Found {len(dq.search_queries)} search queries.", {"decomposition": dq.model_dump()})

    # 2. retrieval
    t0 = time.time()
    yield ev("retrieval", "started", "Searching scientific literature.")
    prov_objs = build_providers(providers)
    papers: List[Paper] = await multi_search(
        dq.search_queries,
        providers=prov_objs,
        max_results_per_provider=max_results_per_provider,
        year_cutoff=year_cutoff,
    )
    telemetry["retrieval_s"] = time.time() - t0
    provider_issues = [
        {"provider": provider.name, "errors": sorted(set(provider.errors))}
        for provider in prov_objs
        if provider.errors
    ]
    retrieval_message = f"Retrieved {len(papers)} unique sources."
    if provider_issues:
        issue_names = ", ".join(item["provider"] for item in provider_issues)
        retrieval_message += f" Some searches failed ({issue_names}); results may be incomplete."
    yield ev(
        "retrieval",
        "completed",
        retrieval_message,
        {
            "paper_count": len(papers),
            "sources": sorted({p.source for p in papers}),
            "provider_issues": provider_issues,
        },
    )

    if not papers:
        if provider_issues:
            failed = ", ".join(item["provider"] for item in provider_issues)
            reason = (
                f"The literature search was incomplete because these sources failed: {failed}. "
                "No scientific conclusion can be drawn from this run; retry or check provider availability."
            )
        else:
            reason = (
                "The enabled literature sources returned no matching papers. "
                "This does not establish that supporting evidence is absent; try broader search terms."
            )
        report = _empty_report(question, dq, telemetry, reason=reason)
        report_message = (
            "Empty report (incomplete literature retrieval)."
            if provider_issues
            else "Empty report (no matching papers)."
        )
        yield ev("report", "completed", report_message, {"report": report.model_dump()})
        return

    # 3. extraction
    t0 = time.time()
    yield ev("extraction", "started", f"Extracting findings from {len(papers)} papers.")
    findings = await extract_findings(papers, llm=llm)
    telemetry["extraction_s"] = time.time() - t0
    yield ev("extraction", "completed", f"Extracted {len(findings)} findings.", {"finding_count": len(findings)})

    # 3b. synthesize a direct answer alongside findings so the UI can answer
    # the user's question instead of only listing speculative hypotheses.
    t0 = time.time()
    yield ev("answer", "started", "Synthesizing a cited answer from the retrieved evidence.")
    answer = await generate_research_answer(question, papers, findings, llm=llm)
    telemetry["answer_s"] = time.time() - t0
    yield ev("answer", "completed", f"Evidence answer: {answer.verdict}.", {"source_count": len(answer.source_ids)})

    # 4. graph build
    t0 = time.time()
    yield ev("graph", "started", "Normalizing entities and building evidence graph.")
    graph, nxg = build_graph(findings)
    telemetry["graph_s"] = time.time() - t0
    yield ev(
        "graph",
        "completed",
        f"Graph: {len(graph.nodes)} nodes / {len(graph.edges)} edges.",
        {"nodes": len(graph.nodes), "edges": len(graph.edges)},
    )

    # 5. multi-hop connections
    t0 = time.time()
    yield ev("connections", "started", "Searching for multi-hop connections.")
    connections = discover_connections(graph, nxg, dq)
    telemetry["connections_s"] = time.time() - t0
    yield ev("connections", "completed", f"Found {len(connections)} candidate connections.", {"count": len(connections)})

    # 6. contradictions
    t0 = time.time()
    yield ev("contradictions", "started", "Detecting conflicting evidence.")
    contradictions = await detect_contradictions(graph, findings, llm=llm)
    telemetry["contradictions_s"] = time.time() - t0
    yield ev("contradictions", "completed", f"Detected {len(contradictions)} potential conflicts.", {"count": len(contradictions)})

    # 7. gaps
    t0 = time.time()
    yield ev("gaps", "started", "Detecting research gaps.")
    gaps = detect_gaps(graph, connections)
    telemetry["gaps_s"] = time.time() - t0
    yield ev("gaps", "completed", f"Identified {len(gaps)} gaps.", {"count": len(gaps)})

    # 8. hypotheses
    t0 = time.time()
    yield ev("hypotheses", "started", "Generating candidate hypotheses.")
    hypotheses = await generate_hypotheses(graph, connections, gaps, dq, llm=llm)
    telemetry["hypotheses_s"] = time.time() - t0
    yield ev("hypotheses", "completed", f"Generated {len(hypotheses)} hypotheses.", {"count": len(hypotheses)})

    # 9. critique
    t0 = time.time()
    yield ev("critique", "started", "Critiquing hypotheses adversarially.")
    hypotheses = await critique_hypotheses(hypotheses, graph, contradictions, llm=llm)
    telemetry["critique_s"] = time.time() - t0
    yield ev("critique", "completed", "Critique attached to each hypothesis.", {"count": len(hypotheses)})

    # 10. final report
    key_findings = _key_findings(findings)
    overall = _overall_confidence(hypotheses)
    report = DiscoveryReport(
        research_question=question,
        decomposition=dq,
        papers=papers,
        findings=findings,
        graph=graph,
        key_findings=key_findings,
        connections=connections,
        contradictions=contradictions,
        gaps=gaps,
        hypotheses=hypotheses,
        answer=answer,
        confidence_summary=overall,
        telemetry=telemetry,
    )
    yield ev("report", "completed", "Final report ready.", {"report": report.model_dump()})


def _key_findings(findings) -> List[str]:
    kf: List[str] = []
    for f in findings:
        if f.status in (EvidenceStatus.ESTABLISHED, EvidenceStatus.SUPPORTED):
            kf.append(f"{f.subject} {f.relationship.replace('_', ' ')} {f.object} ({f.source_id})")
        if len(kf) >= 15:
            break
    return kf


def _overall_confidence(hypotheses) -> str:
    if not hypotheses:
        return "Speculative"
    tally = {"High": 0, "Moderate": 0, "Low": 0, "Speculative": 0}
    for h in hypotheses:
        tally[h.evidence_strength] = tally.get(h.evidence_strength, 0) + 1
    for level in ("High", "Moderate", "Low", "Speculative"):
        if tally[level] > 0:
            return level
    return "Speculative"


def _empty_report(question, dq, telemetry, reason: str) -> DiscoveryReport:
    from backend.models.schemas import EvidenceGraph

    return DiscoveryReport(
        research_question=question,
        decomposition=dq,
        papers=[],
        findings=[],
        graph=EvidenceGraph(),
        key_findings=[reason],
        connections=[],
        contradictions=[],
        gaps=[],
        hypotheses=[],
        answer=ResearchAnswer(
            verdict="insufficient evidence",
            answer=(
                "The search was incomplete, so no scientific conclusion can be drawn from this run."
                if "incomplete" in reason.lower()
                else "No supporting evidence was found among the sources returned by this search; this does not prove that no evidence exists."
            ),
            evidence_summary=reason,
            source_ids=[],
            limitations=["Provider availability and search coverage may limit this result."],
        ),
        confidence_summary="Speculative",
        telemetry=telemetry,
    )
