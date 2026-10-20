"""Retrieval provider interface.

Providers are intentionally modular. Each provider is responsible for
retrieving metadata and abstracts for a single query, and must NEVER
fabricate papers: if an API call fails or returns nothing, it returns
an empty list.
"""
from __future__ import annotations

import abc
import hashlib
import json
import logging
from pathlib import Path
from typing import List, Optional

from backend.config.settings import get_settings
from backend.models.schemas import Paper

logger = logging.getLogger(__name__)


class RetrievalProvider(abc.ABC):
    name: str = "base"

    def __init__(self) -> None:
        self._cache_dir = get_settings().retrieval.cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @abc.abstractmethod
    async def search(self, query: str, max_results: int) -> List[Paper]: ...

    # ----------------- caching helpers -----------------
    def _cache_path(self, query: str, max_results: int) -> Path:
        key = hashlib.sha256(f"{self.name}|{query}|{max_results}".encode()).hexdigest()[:24]
        return self._cache_dir / f"{self.name}-{key}.json"

    def _load_cache(self, query: str, max_results: int) -> Optional[List[Paper]]:
        p = self._cache_path(query, max_results)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            return [Paper.model_validate(x) for x in data]
        except Exception:
            return None

    def _save_cache(self, query: str, max_results: int, papers: List[Paper]) -> None:
        p = self._cache_path(query, max_results)
        p.write_text(json.dumps([x.model_dump() for x in papers], ensure_ascii=False))


def normalize_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    for n in range(4, len(date_str) + 1):
        s = date_str[:n]
        if len(s) >= 4 and s[:4].isdigit():
            try:
                return int(s[:4])
            except Exception:
                return None
    return None
