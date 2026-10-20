"""Hypothesis critique — try to disprove each hypothesis.

The critic runs independently from the generator and is prompted to be
adversarial. Its output is attached to each Hypothesis as a `critique`.
Scores are explainable qualitative judgements, NOT scientific probabilities.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

from backend.models.llm import LLMClient
from backend.models.schemas import (
    Contradiction,
    EvidenceGraph,
    Hypothesis,
    HypothesisCritique,
)

logger = logging.getLogger(__name__)


SYSTEM = """You are an adversarial scientific reviewer. For the hypothesis given, ACTIVELY try
to disprove it. Use ONLY the information in the provided evidence summary — do not invent
contradictory studies.
Address each of:
- weaknesses in the evidence chain
- alternative explanations for the same observations
- any contradictory studies present in the summary
- correlation vs causation concerns
- species / system differences (human vs animal vs cell culture)
- potential publication bias concerns
- whether the relationship is already well established (if so, novelty is low)
- whether the hypothesis is genuinely testable
Scores:
- support_score, contradiction_score, novelty_score, testability_score are in [0,1].
- evidence_quality and overall_confidence are categorical: High / Moderate / Low / Speculative.
- These are qualitative judgements, NOT probabilities. State the reason for each score briefly
  inside the weaknesses or alternative_explanations lists.
"""


async def critique_hypotheses(
    hypotheses: List[Hypothesis],
    graph: EvidenceGraph,
    contradictions: List[Contradiction],
    llm: LLMClient | None = None,
) -> List[Hypothesis]:
    llm = llm or LLMClient()
    if not hypotheses:
        return hypotheses

    labels = {n.id: n.label for n in graph.nodes}
    edges_summary = "\n".join(
        f"- {labels.get(e.source, e.source)} --[{e.relationship}; {e.status}; papers={len(e.papers)}]--> "
        f"{labels.get(e.target, e.target)}"
        for e in graph.edges[:60]
    )
    contradictions_summary = (
        "\n".join(
            f"- {labels.get(c.subject, c.subject)} vs {labels.get(c.object, c.object)}: "
            f"supporting={c.supporting} contradicting={c.contradicting} explanation={c.possible_explanations}"
            for c in contradictions[:20]
        )
        or "(none detected)"
    )

    async def one(h: Hypothesis) -> Hypothesis:
        user = (
            f"Hypothesis: {h.statement}\n"
            f"Rationale: {h.rationale}\n"
            f"Evidence chain refs: {h.evidence_chain}\n"
            f"Supporting findings: {h.supporting_evidence}\n"
            f"Contradictory findings: {h.contradictory_evidence}\n"
            f"Missing links: {h.missing_links}\n\n"
            f"Evidence graph edges:\n{edges_summary}\n\n"
            f"Known contradictions:\n{contradictions_summary}\n"
        )
        try:
            crit = await llm.json(SYSTEM, user, HypothesisCritique)
        except Exception as e:
            logger.warning("Critique failed for %s: %s", h.id, e)
            crit = HypothesisCritique()
        h.critique = crit
        return h

    return list(await asyncio.gather(*(one(h) for h in hypotheses)))
