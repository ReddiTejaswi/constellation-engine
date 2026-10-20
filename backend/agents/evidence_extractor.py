"""Extract atomic scientific findings from paper abstracts.

The LLM is forbidden from inventing missing fields. Each Finding keeps a
pointer back to the source Paper (source_id) and ideally an exact quote.
"""
from __future__ import annotations

import asyncio
import logging
from typing import List

from pydantic import BaseModel, Field

from backend.models.llm import LLMClient
from backend.models.schemas import Finding, Paper

logger = logging.getLogger(__name__)


class _ExtractionResult(BaseModel):
    findings: List[Finding] = Field(default_factory=list)


SYSTEM = """You are an evidence extraction agent for biomedical literature.
Given a paper (title + abstract), extract atomic scientific findings as structured triples.
Rules:
- A finding is a single subject-relationship-object statement actually asserted by the paper
  (not merely mentioned in passing or cited from another work).
- Use short, standardized relationship labels in snake_case,
  e.g. increases_activity_of, inhibits, regulates, encodes, correlates_with,
  reduced_in, required_for, binds, phosphorylates, implicated_in.
- `source_id` MUST equal the provided paper identifier verbatim.
- `source_quote` should be a short sentence copied (or lightly compressed) from the abstract
  that supports the finding. If no clear quote is available, use null.
- Set `evidence_level` based on the described system: human_clinical, human_observational,
  human_tissue, animal, organoid, cell_culture, in_vitro_biochemical, computational,
  theoretical, or unknown.
- Set `evidence_type` to one of: experimental, review, meta_analysis, computational,
  observational, mechanistic, or null if unclear.
- `confidence` reflects how clearly the abstract supports the finding (0-1).
- Set `status` to ESTABLISHED only if the abstract explicitly states the finding is well
  established / replicated; otherwise SUPPORTED. Never use INFERRED/HYPOTHESIS here —
  those are reserved for downstream reasoning.
- Return at most 6 findings per paper. Prefer the most mechanistically informative ones.
- NEVER invent fields. If organism/system are not stated, leave them null.
"""


async def extract_findings(papers: List[Paper], llm: LLMClient | None = None) -> List[Finding]:
    llm = llm or LLMClient()
    sem = asyncio.Semaphore(4)

    async def one(paper: Paper) -> List[Finding]:
        if not paper.abstract:
            return []
        async with sem:
            try:
                user = (
                    f"Paper identifier: {paper.identifier}\n"
                    f"Title: {paper.title}\n"
                    f"Year: {paper.year}\n"
                    f"Abstract:\n{paper.abstract[:4000]}"
                )
                res = await llm.json(SYSTEM, user, _ExtractionResult)
            except Exception as e:
                logger.warning("Extraction failed for %s: %s", paper.identifier, e)
                return []
        out: List[Finding] = []
        for f in res.findings:
            # Enforce provenance integrity: source_id must match the paper.
            f.source_id = paper.identifier
            out.append(f)
        return out

    nested = await asyncio.gather(*(one(p) for p in papers))
    return [f for group in nested for f in group]
