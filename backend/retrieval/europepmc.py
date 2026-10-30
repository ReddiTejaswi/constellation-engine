"""Europe PMC retrieval."""
from __future__ import annotations

import logging
from typing import List

import httpx

from backend.models.schemas import Paper
from backend.retrieval.base import RetrievalProvider, normalize_year

logger = logging.getLogger(__name__)

ENDPOINT = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class EuropePMCProvider(RetrievalProvider):
    name = "europepmc"

    async def search(self, query: str, max_results: int) -> List[Paper]:
        cached = self._load_cache(query, max_results)
        if cached is not None:
            return cached
        params = {
            "query": query,
            "format": "json",
            "pageSize": max_results,
            "resultType": "core",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(ENDPOINT, params=params)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            response = getattr(e, "response", None)
            status = response.status_code if response is not None else "network error"
            self.errors.append(f"HTTP {status}")
            logger.warning("Europe PMC request failed (%s)", status)
            return []
        results = data.get("resultList", {}).get("result", [])
        papers: List[Paper] = []
        for it in results:
            pmid = it.get("pmid")
            doi = it.get("doi")
            ident = f"PMID:{pmid}" if pmid else (f"DOI:{doi}" if doi else f"EPMC:{it.get('id')}")
            authors_raw = it.get("authorList", {}).get("author") or []
            authors = [a.get("fullName") or a.get("lastName") or "" for a in authors_raw]
            authors = [a for a in authors if a]
            date = it.get("firstPublicationDate") or it.get("pubYear")
            url = None
            if pmid:
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif doi:
                url = f"https://doi.org/{doi}"
            papers.append(
                Paper(
                    identifier=ident,
                    title=it.get("title") or "(no title)",
                    authors=authors,
                    publication_date=date,
                    year=normalize_year(date) or (int(it["pubYear"]) if str(it.get("pubYear", "")).isdigit() else None),
                    source="europepmc",
                    url=url,
                    abstract=it.get("abstractText"),
                    journal=(it.get("journalInfo") or {}).get("journal", {}).get("title"),
                    query=query,
                )
            )
        self._save_cache(query, max_results, papers)
        return papers
