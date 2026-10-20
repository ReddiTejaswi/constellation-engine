"""ClinicalTrials.gov retrieval (v2 API)."""
from __future__ import annotations

import logging
from typing import List

import httpx

from backend.models.schemas import Paper
from backend.retrieval.base import RetrievalProvider, normalize_year

logger = logging.getLogger(__name__)

ENDPOINT = "https://clinicaltrials.gov/api/v2/studies"


class ClinicalTrialsProvider(RetrievalProvider):
    name = "clinicaltrials"

    async def search(self, query: str, max_results: int) -> List[Paper]:
        cached = self._load_cache(query, max_results)
        if cached is not None:
            return cached
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(
                    ENDPOINT,
                    params={"query.term": query, "pageSize": max_results, "format": "json"},
                )
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            logger.warning("ClinicalTrials.gov request failed: %s", e)
            return []

        papers: List[Paper] = []
        for study in data.get("studies", []):
            ps = study.get("protocolSection", {})
            idm = ps.get("identificationModule", {})
            dm = ps.get("descriptionModule", {})
            sm = ps.get("statusModule", {})
            nct = idm.get("nctId")
            if not nct:
                continue
            start = sm.get("startDateStruct", {}).get("date")
            papers.append(
                Paper(
                    identifier=f"NCT:{nct}",
                    title=idm.get("briefTitle") or idm.get("officialTitle") or "(no title)",
                    authors=[],
                    publication_date=start,
                    year=normalize_year(start),
                    source="clinicaltrials",
                    url=f"https://clinicaltrials.gov/study/{nct}",
                    abstract=dm.get("briefSummary") or dm.get("detailedDescription"),
                    journal=None,
                    query=query,
                )
            )
        self._save_cache(query, max_results, papers)
        return papers
