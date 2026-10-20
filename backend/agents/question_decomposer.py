"""Decompose a free-form research question into structured scientific concepts."""
from __future__ import annotations

from backend.models.llm import LLMClient
from backend.models.schemas import DecomposedQuestion

SYSTEM = """You are a biomedical research assistant.
Decompose a research question into structured scientific concepts and literature search queries.
Rules:
- Only extract concepts that are explicitly implied by the question OR that are standard
  biomedical synonyms/aliases of entities named in the question.
- Never invent concrete gene/protein/drug names that are not implied by the question.
- Each `search_queries` entry must be a short, concrete literature search string
  (3-10 keywords) that a scientist would plausibly type into PubMed. Produce 3-6 queries
  that explore different angles of the question (mechanistic, phenotypic, therapeutic).
- Return UNKNOWN as empty lists; never fabricate.
"""


async def decompose(question: str, llm: LLMClient | None = None) -> DecomposedQuestion:
    llm = llm or LLMClient()
    user = f"Research question:\n{question}\n\nDecompose it."
    result = await llm.json(SYSTEM, user, DecomposedQuestion)
    result.original_question = question
    if not result.search_queries:
        # fall back to the original question so retrieval still has something
        result.search_queries = [question]
    return result
