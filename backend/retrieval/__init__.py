"""Retrieval provider registry and multi-provider orchestration."""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Type

from backend.config.settings import get_settings
from backend.models.schemas import Paper
from backend.retrieval.base import RetrievalProvider
from backend.retrieval.biorxiv import BioRxivProvider
from backend.retrieval.clinicaltrials import ClinicalTrialsProvider
from backend.retrieval.europepmc import EuropePMCProvider
from backend.retrieval.pubmed import PubMedProvider

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Type[RetrievalProvider]] = {
    PubMedProvider.name: PubMedProvider,
    EuropePMCProvider.name: EuropePMCProvider,
    BioRxivProvider.name: BioRxivProvider,
    ClinicalTrialsProvider.name: ClinicalTrialsProvider,
}


def available_providers() -> List[str]:
    return list(_REGISTRY)


def build_providers(names: Optional[List[str]] = None) -> List[RetrievalProvider]:
    cfg = get_settings().retrieval
    names = names or cfg.providers
    providers: List[RetrievalProvider] = []
    for n in names:
        cls = _REGISTRY.get(n.strip())
        if cls is None:
            logger.warning("Unknown retrieval provider %r, skipping.", n)
            continue
        providers.append(cls())
    return providers


async def multi_search(
    queries: List[str],
    providers: Optional[List[RetrievalProvider]] = None,
    max_results_per_provider: Optional[int] = None,
    year_cutoff: Optional[int] = None,
) -> List[Paper]:
    """Run every query against every provider, de-duplicate, return union."""
    cfg = get_settings().retrieval
    provs = providers or build_providers()
    mrp = max_results_per_provider or cfg.max_results_per_provider

    for provider in provs:
        provider.errors.clear()
    task_providers = [provider for provider in provs for _ in queries]
    tasks = [provider.search(query, mrp) for provider in provs for query in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen: Dict[str, Paper] = {}
    for provider, r in zip(task_providers, results):
        if isinstance(r, Exception):
            provider.errors.append(type(r).__name__)
            logger.warning("Provider %s failed (%s)", provider.name, type(r).__name__)
            continue
        for paper in r:
            if year_cutoff is not None and paper.year and paper.year > year_cutoff:
                continue
            key = paper.identifier
            if key in seen:
                # keep the richest version
                old = seen[key]
                if (len(paper.abstract or "") > len(old.abstract or "")):
                    seen[key] = paper
            else:
                seen[key] = paper
    # Keep the amount sent to extraction/model stages bounded by the user's
    # environment setting. This cap is across all queries and providers.
    return list(seen.values())[: max(0, cfg.max_papers)]
