"""Separate evaluation metrics for the Scientific Discovery Engine.

These functions are intentionally decoupled from the pipeline so that
each metric can be inspected independently. We deliberately do NOT
aggregate them into a single "AI scientific accuracy" number.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List

from backend.graph.builder import _norm
from backend.models.schemas import DiscoveryReport, Finding, Paper


def retrieval_accuracy(papers: List[Paper], gold_identifiers: Iterable[str]) -> Dict[str, Any]:
    gold = {g.strip() for g in gold_identifiers if g.strip()}
    hits = {p.identifier for p in papers} & gold
    return {
        "retrieved": len(papers),
        "gold": len(gold),
        "hits": len(hits),
        "recall": (len(hits) / len(gold)) if gold else None,
    }


def citation_accuracy(findings: List[Finding], papers: List[Paper]) -> Dict[str, Any]:
    pmap = {p.identifier: p for p in papers}
    ok = 0
    bad = []
    for f in findings:
        p = pmap.get(f.source_id)
        if not p or not (p.abstract or ""):
            bad.append({"source_id": f.source_id, "reason": "paper missing or no abstract"})
            continue
        quote = (f.source_quote or "").strip().lower()
        if not quote:
            # count presence of subject + object in the abstract as a weak support
            abs_text = (p.abstract or "").lower()
            if _norm(f.subject) in _norm(abs_text) and _norm(f.object) in _norm(abs_text):
                ok += 1
            else:
                bad.append({"source_id": f.source_id, "reason": "subject/object not found in abstract"})
            continue
        if quote[:60] in (p.abstract or "").lower():
            ok += 1
        else:
            # fuzzy
            r = SequenceMatcher(None, quote[:120], (p.abstract or "").lower()).ratio()
            if r >= 0.6:
                ok += 1
            else:
                bad.append({"source_id": f.source_id, "reason": f"quote not substantiated (ratio={r:.2f})"})
    return {
        "findings": len(findings),
        "cited_ok": ok,
        "cited_bad": len(findings) - ok,
        "ratio": (ok / len(findings)) if findings else None,
        "problems": bad[:20],
    }


def graph_integrity(report: DiscoveryReport) -> Dict[str, Any]:
    node_ids = {n.id for n in report.graph.nodes}
    orphan_edges = [e.id for e in report.graph.edges if e.source not in node_ids or e.target not in node_ids]
    edges_without_papers = [e.id for e in report.graph.edges if not e.papers]
    return {
        "nodes": len(report.graph.nodes),
        "edges": len(report.graph.edges),
        "orphan_edges": orphan_edges,
        "edges_without_papers": edges_without_papers,
    }


def hypothesis_quality(report: DiscoveryReport) -> Dict[str, Any]:
    out = []
    for h in report.hypotheses:
        out.append({
            "id": h.id,
            "testable_prediction_present": bool(h.testable_prediction),
            "suggested_experiment_present": bool(h.suggested_experiment),
            "evidence_chain_len": len(h.evidence_chain),
            "evidence_strength": h.evidence_strength,
            "critique_support_score": h.critique.support_score if h.critique else None,
            "critique_contradiction_score": h.critique.contradiction_score if h.critique else None,
            "critique_overall": h.critique.overall_confidence if h.critique else None,
        })
    return {"count": len(report.hypotheses), "hypotheses": out}


def connection_integrity(report: DiscoveryReport) -> Dict[str, Any]:
    edge_ids = {e.id for e in report.graph.edges}
    broken = []
    for c in report.connections:
        for eid in c.supporting_edges:
            if eid not in edge_ids:
                broken.append({"path": c.path, "missing_edge": eid})
    return {
        "connections": len(report.connections),
        "direct": sum(1 for c in report.connections if c.direct_evidence),
        "inferred": sum(1 for c in report.connections if not c.direct_evidence),
        "broken_support_edges": broken,
    }
