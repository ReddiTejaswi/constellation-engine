"""Generate 1-3 evidence-backed hypotheses from inferred connections + gaps."""
from __future__ import annotations

import logging
from typing import List

from pydantic import BaseModel, Field

from backend.models.llm import LLMClient
from backend.models.schemas import (
    Connection,
    DecomposedQuestion,
    EvidenceGraph,
    EvidenceStatus,
    Hypothesis,
    ResearchGap,
)

logger = logging.getLogger(__name__)


class _HypothesisList(BaseModel):
    hypotheses: List[Hypothesis] = Field(default_factory=list)


SYSTEM = """You are a cautious biomedical research assistant that proposes TESTABLE hypotheses
based strictly on the provided evidence graph summary.
Hard rules:
- Produce AT MOST 3 hypotheses. Prefer 1-2 strong ones over many weak ones.
- Every hypothesis MUST be grounded in the provided connections/edges. Do NOT introduce
  entities that are not in the graph summary.
- status MUST remain HYPOTHESIS.
- Never claim a treatment works. Never claim medical efficacy. Avoid "cures", "proves", "shows".
- `testable_prediction` must describe a specific, measurable experimental outcome.
- `suggested_experiment` must be concrete (model system, intervention, readout).
- `expected_if_correct` and `expected_if_wrong` must be clearly distinguishable.
- `evidence_strength` must be one of: High, Moderate, Low, Speculative. It is High ONLY if every
  edge in the chain has multiple supporting papers; otherwise Moderate at best for a chain of
  length >=3 with single-paper edges; Low if evidence is sparse; Speculative if the chain relies
  on cross-species or in-vitro-only data.
- `novelty` should describe what makes the connection non-obvious ("multi-hop across 3 studies",
  "crosses disciplines X and Y", "contradicts common assumption Z").
- id should be like H1, H2, H3.
"""


async def generate_hypotheses(
    graph: EvidenceGraph,
    connections: List[Connection],
    gaps: List[ResearchGap],
    dq: DecomposedQuestion,
    llm: LLMClient | None = None,
) -> List[Hypothesis]:
    llm = llm or LLMClient()
    if not connections and not gaps:
        return []
    labels = {n.id: n.label for n in graph.nodes}
    edges_by_id = {e.id: e for e in graph.edges}

    def _summarize(c: Connection) -> str:
        parts = []
        for i, eid in enumerate(c.supporting_edges):
            e = edges_by_id.get(eid)
            if not e:
                continue
            parts.append(
                f"  edge {i+1}: {labels.get(e.source, e.source)} --[{e.relationship}; "
                f"status={e.status}; papers={e.papers}]--> {labels.get(e.target, e.target)}"
            )
        return "\n".join(parts)

    top_conns = [c for c in connections if not c.direct_evidence][:6]
    conn_text = "\n\n".join(
        f"Connection {i+1} ({' -> '.join(c.path_labels)}): {c.rationale}\n{_summarize(c)}"
        for i, c in enumerate(top_conns)
    )
    gap_text = "\n".join(
        f"- {g.description}" for g in gaps[:6]
    ) or "(none)"
    user = (
        f"Research question:\n{dq.original_question}\n\n"
        f"Candidate multi-hop connections (INFERRED):\n{conn_text or '(none)'}\n\n"
        f"Identified research gaps:\n{gap_text}\n\n"
        "Propose 1-3 hypotheses grounded strictly in the above."
    )
    res = await llm.json(SYSTEM, user, _HypothesisList)
    out: List[Hypothesis] = []
    for i, h in enumerate(res.hypotheses[:3]):
        h.id = h.id or f"H{i+1}"
        h.status = EvidenceStatus.HYPOTHESIS
        out.append(h)
    return out
