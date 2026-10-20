"""Contradiction detection.

Rule-based first pass over the evidence graph: for every (subject,object)
pair that has conflicting relationships (e.g. "increases" vs "inhibits",
"protects" vs "damages"), flag a Contradiction and ask the LLM for
plausible explanations grounded only in the two provided quotes.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Tuple

from pydantic import BaseModel

from backend.models.llm import LLMClient
from backend.models.schemas import Contradiction, EvidenceGraph, Finding

logger = logging.getLogger(__name__)


# A tiny antonym table for canonical relationship clashes. Downstream the LLM
# can suggest nuanced explanations; this table only decides *where* to look.
ANTONYMS: Dict[str, List[str]] = {
    "increases": ["decreases", "reduces", "inhibits", "suppresses", "downregulates"],
    "increases_activity_of": ["decreases_activity_of", "inhibits", "suppresses"],
    "activates": ["inhibits", "suppresses", "downregulates"],
    "upregulates": ["downregulates", "represses"],
    "promotes": ["prevents", "inhibits", "suppresses", "protects_against"],
    "protects": ["damages", "promotes_damage", "exacerbates"],
    "required_for": ["dispensable_for"],
    "reduced_in": ["elevated_in", "increased_in"],
    "causes": ["prevents"],
}


def _antonym(rel: str) -> List[str]:
    rel = rel.lower()
    out: List[str] = []
    for k, vs in ANTONYMS.items():
        if rel == k:
            out.extend(vs)
        if rel in vs:
            out.append(k)
    return out


class _Explain(BaseModel):
    possible_explanations: List[str] = []
    resolution: str = "Currently unresolved."
    confidence: str = "Moderate"


EXPLAIN_SYSTEM = """You examine two conflicting biomedical findings and propose plausible
explanations for the discrepancy, grounded ONLY in the provided quotes/metadata.
Consider: different organisms, cell types, tissues, disease stage, dosage, treatment
duration, methodology, sample size, genetic background, environmental conditions.
- Do NOT pick a winner. Return `resolution`: "Currently unresolved." unless one
  study clearly supersedes the other based on the provided information.
- confidence must be one of: Low, Moderate, High (High only when the resolution
  is clearly stated in the evidence).
"""


async def detect_contradictions(
    graph: EvidenceGraph,
    findings: List[Finding],
    llm: LLMClient | None = None,
    *,
    max_pairs: int = 10,
) -> List[Contradiction]:
    f_by_id = {f"F{i:04d}": f for i, f in enumerate(findings)}
    # index edges by (subject,object) pair (ignoring direction)
    pair_edges: Dict[Tuple[str, str], List] = defaultdict(list)
    for e in graph.edges:
        key = tuple(sorted([e.source, e.target]))
        pair_edges[key].append(e)

    contradictions: List[Contradiction] = []
    llm = llm or LLMClient()

    for key, edges in pair_edges.items():
        if len(edges) < 2:
            continue
        # find at least one antonym pair
        for i in range(len(edges)):
            for j in range(i + 1, len(edges)):
                r1 = edges[i].relationship
                r2 = edges[j].relationship
                if r2 in _antonym(r1):
                    supporting = edges[i].supporting_findings
                    contradicting = edges[j].supporting_findings
                    s_quote = _quote(f_by_id, supporting)
                    c_quote = _quote(f_by_id, contradicting)
                    s_meta = _meta(f_by_id, supporting)
                    c_meta = _meta(f_by_id, contradicting)
                    user = (
                        "Finding A:\n"
                        f"- relationship: {r1}\n"
                        f"- quote: {s_quote}\n"
                        f"- metadata: {s_meta}\n\n"
                        "Finding B (apparent contradiction):\n"
                        f"- relationship: {r2}\n"
                        f"- quote: {c_quote}\n"
                        f"- metadata: {c_meta}\n"
                    )
                    try:
                        expl = await llm.json(EXPLAIN_SYSTEM, user, _Explain)
                    except Exception as e:  # pragma: no cover
                        logger.warning("Contradiction explain failed: %s", e)
                        expl = _Explain()
                    conf = expl.confidence if expl.confidence in ("Low", "Moderate", "High") else "Moderate"
                    contradictions.append(
                        Contradiction(
                            subject=edges[i].source,
                            object=edges[i].target,
                            supporting=supporting,
                            contradicting=contradicting,
                            possible_explanations=expl.possible_explanations,
                            resolution=expl.resolution or "Currently unresolved.",
                            confidence=conf,  # type: ignore[arg-type]
                        )
                    )
                    if len(contradictions) >= max_pairs:
                        return contradictions
    return contradictions


def _quote(f_by_id, fids):
    for fid in fids:
        f = f_by_id.get(fid)
        if f and f.source_quote:
            return f.source_quote
    return "(no quote)"


def _meta(f_by_id, fids):
    for fid in fids:
        f = f_by_id.get(fid)
        if not f:
            continue
        return (
            f"organism={f.organism or 'unknown'}; system={f.system or 'unknown'}; "
            f"evidence_level={f.evidence_level}; source={f.source_id}"
        )
    return "unknown"
