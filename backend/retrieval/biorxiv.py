"""bioRxiv retrieval via Europe PMC preprint index (simpler + works offline-safe).

bioRxiv's native API does not support full-text keyword search well, so we
go through Europe PMC filtered to preprints. This keeps a single API call
and consistent metadata.
"""
from __future__ import annotations

from typing import List

from backend.models.schemas import Paper
from backend.retrieval.base import RetrievalProvider
from backend.retrieval.europepmc import EuropePMCProvider


class BioRxivProvider(RetrievalProvider):
    name = "biorxiv"

    async def search(self, query: str, max_results: int) -> List[Paper]:
        cached = self._load_cache(query, max_results)
        if cached is not None:
            return cached
        epmc = EuropePMCProvider()
        results = await epmc.search(f"({query}) AND SRC:PPR", max_results)
        for r in results:
            r.source = "biorxiv/preprint"
        self._save_cache(query, max_results, results)
        return results
