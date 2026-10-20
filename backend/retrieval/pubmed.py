"""PubMed retrieval via NCBI E-utilities (esearch + efetch)."""
from __future__ import annotations

import logging
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
                esearch = await client.get(
                    f"{BASE}/esearch.fcgi",
                    params={**base_params, "db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"},
                )
                esearch.raise_for_status()
                ids = esearch.json().get("esearchresult", {}).get("idlist", [])
                if not ids:
                    self._save_cache(query, max_results, [])
                    return []
                efetch = await client.get(
                    f"{BASE}/efetch.fcgi",
                    params={**base_params, "db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
                )
                efetch.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("PubMed request failed: %s", e)
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
