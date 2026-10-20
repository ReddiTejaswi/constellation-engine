"""Environment-driven configuration.

The model name is NEVER hardcoded. It must be provided through the
`MODEL_NAME` environment variable. The same applies to the base URL and
API key: the application targets any OpenAI-compatible endpoint.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

# Auto-load a local .env (if present) so `cp .env.example .env` + run just works.
# python-dotenv is optional; if unavailable we silently fall back to the real env.
try:  # pragma: no cover
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:  # pragma: no cover
    pass


class ModelConfig(BaseModel):
    name: str = Field(..., description="LLM model identifier (env: MODEL_NAME)")
    base_url: str = Field(..., description="OpenAI-compatible base URL")
    api_key: str = Field(..., description="API key for the model endpoint")
    temperature: float = 0.2
    max_tokens: int = 2048
    request_timeout: int = 120


class RetrievalConfig(BaseModel):
    providers: List[str]
    max_results_per_provider: int = 8
    cache_dir: Path = Path("./data/retrieval_cache")
    ncbi_api_key: Optional[str] = None
    ncbi_tool: str = "scientific-discovery-engine"
    ncbi_email: Optional[str] = None


class Settings(BaseModel):
    model: ModelConfig
    retrieval: RetrievalConfig
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    benchmark_cutoff_year: int = 1999


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    model_name = _env("MODEL_NAME")
    model_base_url = _env("MODEL_BASE_URL")
    model_api_key = _env("MODEL_API_KEY")

    missing = [k for k, v in {
        "MODEL_NAME": model_name,
        "MODEL_BASE_URL": model_base_url,
        "MODEL_API_KEY": model_api_key,
    }.items() if not v]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". The model configuration is strictly environment-driven; "
            + "see .env.example."
        )

    providers = [p.strip() for p in _env("RETRIEVAL_PROVIDERS", "pubmed,europepmc").split(",") if p.strip()]

    return Settings(
        model=ModelConfig(
            name=model_name,  # type: ignore[arg-type]
            base_url=model_base_url,  # type: ignore[arg-type]
            api_key=model_api_key,  # type: ignore[arg-type]
            temperature=float(_env("MODEL_TEMPERATURE", "0.2")),
            max_tokens=int(_env("MODEL_MAX_TOKENS", "2048")),
            request_timeout=int(_env("MODEL_REQUEST_TIMEOUT", "120")),
        ),
        retrieval=RetrievalConfig(
            providers=providers,
            max_results_per_provider=int(_env("RETRIEVAL_MAX_RESULTS_PER_PROVIDER", "8")),
            cache_dir=Path(_env("RETRIEVAL_CACHE_DIR", "./data/retrieval_cache")),
            ncbi_api_key=_env("NCBI_API_KEY"),
            ncbi_tool=_env("NCBI_TOOL", "scientific-discovery-engine"),
            ncbi_email=_env("NCBI_EMAIL"),
        ),
        host=_env("HOST", "0.0.0.0"),
        port=int(_env("PORT", "8000")),
        log_level=_env("LOG_LEVEL", "INFO"),
        benchmark_cutoff_year=int(_env("BENCHMARK_CUTOFF_YEAR", "1999")),
    )
