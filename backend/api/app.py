"""FastAPI application exposing the discovery pipeline."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import OrderedDict, deque
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.agents.pipeline import run_pipeline, stream_pipeline
from backend.benchmark.historical import list_benchmarks, run_benchmark
from backend.config.settings import get_settings
from backend.retrieval import available_providers, build_providers, multi_search

logger = logging.getLogger(__name__)


def _credit_exhaustion_message(error: Exception) -> Optional[str]:
    """Return a safe, actionable message for exhausted Token Factory credits."""
    message = str(error).lower()
    markers = (
        "402",
        "payment_required",
        "payment required",
        "insufficient_quota",
        "insufficient quota",
        "insufficient balance",
        "insufficient credits",
        "insufficient account balance",
        "not enough balance",
        "balance is negative",
        "credit balance",
        "credits exhausted",
        "out of credits",
        "quota exceeded",
    )
    if any(marker in message for marker in markers):
        return (
            "Your Nebius Token Factory hackathon credits or balance are exhausted, so this investigation stopped. "
            "Try again if more hackathon credits become available."
        )
    return None

app = FastAPI(title="Scientific Discovery Engine")
app.state.demo_ai_running = False

_DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() in {"1", "true", "yes", "on"}
_RATE_LIMIT = max(1, int(os.environ.get("DEMO_REQUESTS_PER_HOUR", "8")))
_RATE_WINDOW = 3600
_RATE_LIMITED_PATHS = {
    "/api/investigate",
    "/api/investigate/stream",
    "/api/search",
    "/api/benchmark/run",
}
_request_times: OrderedDict[str, deque[float]] = OrderedDict()


@app.middleware("http")
async def secure_demo_requests(request: Request, call_next):
    if request.method == "POST" and request.url.path in _RATE_LIMITED_PATHS:
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > 65536:
                    return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid content length."})
    if _DEMO_MODE and request.method == "POST" and request.url.path in _RATE_LIMITED_PATHS:
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.rsplit(",", 1)[-1].strip() or client_ip
        now = time.monotonic()
        events = _request_times.setdefault(client_ip, deque())
        while events and now - events[0] >= _RATE_WINDOW:
            events.popleft()
        if len(events) >= _RATE_LIMIT:
            return JSONResponse(
                status_code=429,
                content={"detail": "Demo request limit reached. Please try again later."},
                headers={"Retry-After": str(max(1, int(_RATE_WINDOW - (now - events[0]))))},
            )
        events.append(now)
        _request_times.move_to_end(client_ip)
        while len(_request_times) > 2048:
            _request_times.popitem(last=False)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    if os.environ.get("RENDER"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


class InvestigateRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    providers: Optional[List[str]] = Field(default=None, max_length=4)
    year_cutoff: Optional[int] = Field(default=None, ge=1900, le=2100)
    max_results_per_provider: Optional[int] = Field(default=None, ge=1, le=20)


class SearchRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    providers: Optional[List[str]] = Field(default=None, max_length=4)
    max_results_per_provider: Optional[int] = Field(default=None, ge=1, le=20)


@app.get("/api/health")
async def health():
    s = get_settings()
    return {
        "status": "ok",
        "model": s.model.name,
        "model_enabled": s.model_enabled,
        "providers_available": available_providers(),
        "providers_enabled": s.retrieval.providers,
    }


@app.post("/api/investigate")
async def investigate(req: InvestigateRequest):
    if not get_settings().model_enabled:
        raise HTTPException(status_code=503, detail="AI analysis is paused. Use Search APIs only or set MODEL_ENABLED=true.")
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    if _DEMO_MODE and app.state.demo_ai_running:
        raise HTTPException(status_code=429, detail="Another demo analysis is running. Please retry shortly.")
    if _DEMO_MODE:
        app.state.demo_ai_running = True
    try:
        report = await run_pipeline(
            req.question,
            providers=req.providers,
            year_cutoff=req.year_cutoff,
            max_results_per_provider=req.max_results_per_provider,
        )
    except Exception as e:
        logger.exception("Pipeline failed")
        credit_message = _credit_exhaustion_message(e)
        raise HTTPException(
            status_code=402 if credit_message else 500,
            detail=credit_message or "The investigation failed. Check server logs and try again.",
        )
    finally:
        if _DEMO_MODE:
            app.state.demo_ai_running = False
    return report.model_dump()


@app.post("/api/investigate/stream")
async def investigate_stream(req: InvestigateRequest):
    if not get_settings().model_enabled:
        raise HTTPException(status_code=503, detail="AI analysis is paused. Use Search APIs only or set MODEL_ENABLED=true.")
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    if _DEMO_MODE and app.state.demo_ai_running:
        raise HTTPException(status_code=429, detail="Another demo analysis is running. Please retry shortly.")
    if _DEMO_MODE:
        app.state.demo_ai_running = True

    async def gen():
        try:
            async for ev in stream_pipeline(
                req.question,
                providers=req.providers,
                year_cutoff=req.year_cutoff,
                max_results_per_provider=req.max_results_per_provider,
            ):
                payload = {
                    "stage": ev.stage,
                    "status": ev.status,
                    "message": ev.message,
                    "data": ev.data,
                    "ts": ev.ts,
                }
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            logger.exception("Stream failed")
            message = _credit_exhaustion_message(e) or "The investigation failed. Check server logs and try again."
            yield f"data: {json.dumps({'stage': 'error', 'status': 'error', 'message': message})}\n\n"
        finally:
            if _DEMO_MODE:
                app.state.demo_ai_running = False

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/search")
async def search_literature(req: SearchRequest):
    """Search literature providers directly; this route never calls the model."""
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    lowered = question.lower()
    if "diabet" in lowered and "stem" in lowered:
        queries = [
            "stem cell AND diabetes mellitus",
            "islet stem cell therapy type 1 diabetes",
            "stem cell-derived islets diabetes",
        ]
    elif "diabet" in lowered and any(term in lowered for term in ("gene", "edit", "crispr", "genetic", "manipulat")):
        queries = [
            '"gene-edited" islet cells type 1 diabetes',
            "CRISPR edited pancreatic islet cells diabetes",
            "genetically modified beta cells diabetes clinical trial",
        ]
    else:
        queries = [question]

    providers = build_providers(req.providers)
    papers = await multi_search(
        queries,
        providers=providers,
        max_results_per_provider=req.max_results_per_provider,
    )

    relevance_terms = ("gene edit", "gene-edit", "crispr", "genetic modif", "islet", "beta cell", "type 1 diabetes", "diabetes")

    def relevance(paper):
        title = paper.title.lower()
        abstract = (paper.abstract or "").lower()
        return (
            sum(3 for term in relevance_terms if term in title)
            + sum(1 for term in relevance_terms if term in abstract)
        )

    papers.sort(key=lambda paper: (relevance(paper), paper.year or 0), reverse=True)
    return {
        "question": question,
        "queries_used": queries,
        "count": len(papers),
        "papers": [paper.model_dump() for paper in papers],
        "provider_issues": [
            {"provider": provider.name, "errors": sorted(set(provider.errors))}
            for provider in providers
            if provider.errors
        ],
        "model_called": False,
    }


@app.get("/api/benchmarks")
async def benchmarks():
    return {"benchmarks": list_benchmarks()}


class BenchmarkRequest(BaseModel):
    benchmark_id: str


@app.post("/api/benchmark/run")
async def benchmark_run(req: BenchmarkRequest):
    if not get_settings().model_enabled:
        raise HTTPException(status_code=503, detail="AI analysis is paused. Set MODEL_ENABLED=true to run benchmarks.")
    if _DEMO_MODE and app.state.demo_ai_running:
        raise HTTPException(status_code=429, detail="Another demo analysis is running. Please retry shortly.")
    if _DEMO_MODE:
        app.state.demo_ai_running = True
    try:
        return await run_benchmark(req.benchmark_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown benchmark")
    except Exception as e:
        logger.exception("Benchmark failed")
        credit_message = _credit_exhaustion_message(e)
        raise HTTPException(
            status_code=402 if credit_message else 500,
            detail=credit_message or "The benchmark failed. Check server logs and try again.",
        )
    finally:
        if _DEMO_MODE:
            app.state.demo_ai_running = False


# ------------------------- Frontend static ------------------------
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIR.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/{path:path}")
    async def spa(path: str):
        f = FRONTEND_DIR / path
        if f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    @app.get("/")
    async def index_dev():
        return {"message": "Frontend not built. Run `npm run build` in frontend/."}
