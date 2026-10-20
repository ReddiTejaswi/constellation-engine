"""FastAPI application exposing the discovery pipeline."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from backend.agents.pipeline import run_pipeline, stream_pipeline
from backend.benchmark.historical import list_benchmarks, run_benchmark
from backend.config.settings import get_settings
from backend.retrieval import available_providers

logger = logging.getLogger(__name__)

app = FastAPI(title="Scientific Discovery Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class InvestigateRequest(BaseModel):
    question: str
    providers: Optional[List[str]] = None
    year_cutoff: Optional[int] = None
    max_results_per_provider: Optional[int] = None


@app.get("/api/health")
async def health():
    s = get_settings()
    return {
        "status": "ok",
        "model": s.model.name,
        "providers_available": available_providers(),
        "providers_enabled": s.retrieval.providers,
    }


@app.post("/api/investigate")
async def investigate(req: InvestigateRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    try:
        report = await run_pipeline(
            req.question,
            providers=req.providers,
            year_cutoff=req.year_cutoff,
            max_results_per_provider=req.max_results_per_provider,
        )
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))
    return report.model_dump()


@app.post("/api/investigate/stream")
async def investigate_stream(req: InvestigateRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

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
            yield f"data: {json.dumps({'stage': 'error', 'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/benchmarks")
async def benchmarks():
    return {"benchmarks": list_benchmarks()}


class BenchmarkRequest(BaseModel):
    benchmark_id: str


@app.post("/api/benchmark/run")
async def benchmark_run(req: BenchmarkRequest):
    try:
        return await run_benchmark(req.benchmark_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown benchmark")
    except Exception as e:
        logger.exception("Benchmark failed")
        raise HTTPException(status_code=500, detail=str(e))


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
