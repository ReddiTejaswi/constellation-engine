"""PubMed retrieval via NCBI E-utilities (esearch + efetch)."""
from __future__ import annotations

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from typing import List, Optional

import httpx

from backend.config.settings import get_settings
from backend.models.schemas import Paper
from backend.retrieval.base import RetrievalProvider, normalize_year

logger = logging.getLogger(__name__)

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedProvider(RetrievalProvider):
    name = "pubmed"

    def __init__(self) -> None:
        super().__init__()
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
        """Serialize E-utilities requests and retry brief rate-limit responses."""
        cfg = get_settings().retrieval
        min_interval = 0.11 if cfg.ncbi_api_key else 0.35

        for attempt in range(3):
            async with self._request_lock:
                delay = min_interval - (time.monotonic() - self._last_request_at)
                if delay > 0:
                    await asyncio.sleep(delay)
                response = await client.get(url, params=params)
                self._last_request_at = time.monotonic()

            if response.status_code == 429 and attempt < 2:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = max(float(retry_after), 0.5) if retry_after else 1.0 * (attempt + 1)
                except ValueError:
                    delay = 1.0 * (attempt + 1)
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()
            return response

        raise RuntimeError("PubMed request retry limit reached")

    async def search(self, query: str, max_results: int) -> List[Paper]:
        cached = self._load_cache(query, max_results)
        if cached is not None:
            return cached

        cfg = get_settings().retrieval
        base_params = {"tool": cfg.ncbi_tool}
        if cfg.ncbi_email:
            base_params["email"] = cfg.ncbi_email
        if cfg.ncbi_api_key:
            base_params["api_key"] = cfg.ncbi_api_key

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                esearch = await self._get(
                    client,
                    f"{BASE}/esearch.fcgi",
                    {**base_params, "db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"},
                )
                ids = esearch.json().get("esearchresult", {}).get("idlist", [])
                if not ids:
                    self._save_cache(query, max_results, [])
                    return []
                efetch = await self._get(
                    client,
                    f"{BASE}/efetch.fcgi",
                    {**base_params, "db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
                )
        except httpx.HTTPError as e:
            response = getattr(e, "response", None)
            status = response.status_code if response is not None else "network error"
            self.errors.append(f"HTTP {status}")
            logger.warning("PubMed request failed (%s)", status)
            return []
        except Exception as e:
            self.errors.append(type(e).__name__)
            logger.warning("PubMed request failed (%s)", type(e).__name__)
            return []

        papers = _parse_pubmed_xml(efetch.text, query)
        self._save_cache(query, max_results, papers)
        return papers


def _parse_pubmed_xml(xml_text: str, query: str) -> List[Paper]:
    out: List[Paper] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("PubMed XML parse failed: %s", e)
        return out

    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text if pmid_el is not None else None
        if not pmid:
            continue
        title_el = article.find(".//ArticleTitle")
        title = _text(title_el) or "(no title)"
        abstract = " ".join(
            _text(x) or "" for x in article.findall(".//Abstract/AbstractText")
        ).strip() or None
        journal_el = article.find(".//Journal/Title")
        journal = _text(journal_el)
        authors: List[str] = []
        for a in article.findall(".//AuthorList/Author"):
            ln = _text(a.find("LastName"))
            fn = _text(a.find("ForeName"))
            if ln or fn:
                authors.append(" ".join(x for x in [fn, ln] if x))
        date = _article_date(article)
        out.append(
            Paper(
                identifier=f"PMID:{pmid}",
                title=title,
                authors=authors,
                publication_date=date,
                year=normalize_year(date),
                source="pubmed",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                abstract=abstract,
                journal=journal,
                query=query,
            )
        )
    return out


def _text(el) -> Optional[str]:
    if el is None:
        return None
    # Use itertext to flatten italic/bold tags inside abstracts.
    return "".join(el.itertext()).strip() or None


def _article_date(article) -> Optional[str]:
    for path in (".//ArticleDate", ".//PubDate", ".//DateCreated"):
        d = article.find(path)
        if d is None:
            continue
        y = _text(d.find("Year"))
        m = _text(d.find("Month")) or "01"
        day = _text(d.find("Day")) or "01"
        if y:
            try:
                mi = int(m) if m.isdigit() else {
                    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
                }.get(m[:3], 1)
                di = int(day) if day.isdigit() else 1
                return f"{int(y):04d}-{mi:02d}-{di:02d}"
            except Exception:
                return y
    return None
