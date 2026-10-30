# Scientific Discovery Engine

An AI research agent that helps scientists discover potential **connections**
between fragmented scientific findings across papers, experiments, disciplines
and time periods.

> The AI connects the dots; scientists validate the dots experimentally.

The system does **not** claim to discover or prove scientific truth. It
retrieves evidence, extracts structured findings, builds an evidence graph with
preserved provenance, finds multi-hop connections, flags contradictions and
research gaps, and proposes a small number of **testable hypotheses** —
every one of which is adversarially critiqued and labelled as a hypothesis,
never as fact.

---

## 1. Pipeline

```
User research question
    ↓ decomposition         (concepts, synonyms, search queries)
    ↓ retrieval             (PubMed, Europe PMC, bioRxiv, ClinicalTrials.gov …)
    ↓ evidence extraction   (atomic subject-relationship-object findings)
    ↓ evidence answer       (direct, cited answer grounded in retrieved papers)
    ↓ graph build           (entity normalization + evidence provenance)
    ↓ multi-hop connections (INFERRED unless directly supported)
    ↓ contradiction scan    (antonym-based + LLM explanation)
    ↓ research-gap scan     (end-to-end pairs with no direct study)
    ↓ hypothesis generation (1–3, grounded in the graph)
    ↓ hypothesis critique   (adversarial, qualitative scores)
    → Final DiscoveryReport
```

Each stage is a dedicated module in `backend/agents/`.

## 2. Hard rules

- **Model name is not hardcoded.** It is read from `MODEL_NAME` and the base URL
  / API key come from `MODEL_BASE_URL` / `MODEL_API_KEY`. A test enforces that
  no provider-specific model name appears in the backend package.
- **Provenance is mandatory.** Every graph edge keeps the list of papers that
  support it; every finding keeps its `source_id` and (where possible) a direct
  quote.
- **Evidence status is never silently upgraded.** `INFERRED` and `HYPOTHESIS`
  stay as such — only direct experimental support can establish a relationship.
- **No fabricated papers / authors / results.** Retrieval returns an empty list
  if no evidence is found; the pipeline then reports *"No supporting evidence
  found in the searched sources."*
- **Hypotheses are hypotheses.** The frontend uses visually distinct pills for
  `ESTABLISHED / SUPPORTED / INFERRED / HYPOTHESIS / UNKNOWN` and never implies
  numerical scientific certainty.

## 3. Repository layout

```
scientific-discovery-engine/
├── backend/
│   ├── api/           # FastAPI app + SSE streaming
│   ├── agents/        # one module per pipeline stage
│   ├── retrieval/     # pluggable providers (pubmed, europepmc, biorxiv, …)
│   ├── graph/         # entity normalization + evidence graph
│   ├── models/        # pydantic schemas + LLM client
│   ├── benchmark/     # historical discovery benchmarks (e.g. optogenetics)
│   ├── evaluation/    # separate retrieval / citation / graph metrics
│   └── config/        # env-driven settings (strict)
├── frontend/          # React + Vite + reactflow
├── tests/             # pytest; mocks the LLM, exercises graph & agents
├── .env.example
└── README.md
```

## 4. Running

### Requirements

- Python 3.13
- Node 20+
- An OpenAI-compatible chat completions endpoint (e.g. a Nebius / NVIDIA / local
  vLLM / OpenRouter deployment of your choice)

### Backend

```bash
cp .env.example .env
# Edit .env and provide at least MODEL_NAME, MODEL_BASE_URL, MODEL_API_KEY.

python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m backend.server
# → serves on http://${HOST:-0.0.0.0}:${PORT:-8000}
```

### Frontend

```bash
cd frontend
npm install
npm run build            # production bundle, served by FastAPI at /
# or during development:
npm run dev              # http://localhost:5173, proxies /api → :8000
```

If `frontend/dist` exists, the FastAPI app serves it from `/` directly, so a
single process is enough in production.

### Tests

```bash
.venv/bin/python -m pytest -q
```

Includes a test that **fails if any hardcoded model name** (`gpt-4`,
`claude-`, etc.) is found in the backend source tree.

## 5. API

| Method | Path                      | Purpose |
|--------|---------------------------|---------|
| GET    | `/api/health`             | Model + enabled retrieval providers |
| POST   | `/api/investigate`        | Run the full pipeline, return the final `DiscoveryReport` |
| POST   | `/api/investigate/stream` | Server-sent events — one event per stage, final report included |
| GET    | `/api/benchmarks`         | List historical benchmarks |
| POST   | `/api/benchmark/run`      | Run a benchmark (`{"benchmark_id": "optogenetics"}`), returns report + metrics |

Example:

```bash
curl -s http://localhost:8000/api/investigate \
  -H 'Content-Type: application/json' \
  -d '{"question":"What mechanisms could explain resistance to EGFR inhibitors in NSCLC?"}'
```

## 6. Retrieval providers

Enabled through `RETRIEVAL_PROVIDERS` (comma-separated). Supported names:

- `pubmed` — NCBI E-utilities (esearch + efetch).
- `europepmc` — Europe PMC REST API.
- `biorxiv` — bioRxiv/medRxiv preprints via Europe PMC's `SRC:PPR` filter.
- `clinicaltrials` — ClinicalTrials.gov v2 API.

Adding a new provider = subclass `RetrievalProvider` in
`backend/retrieval/` and register it in `backend/retrieval/__init__.py`.
Results are cached under `RETRIEVAL_CACHE_DIR` so re-runs are fast.

## 7. Benchmark mode

Historical cases where multiple intermediate findings later became part of a
major discovery:

- `optogenetics` (cutoff 2004)
- `helicobacter_ulcers` (cutoff 1983)

Retrieval is restricted to literature published **before** the cutoff year.
Metrics reported (separately, never a single score):

- entities recovered (recall against the reference list)
- multi-hop connections recovered
- hypothesis similarity vs the historical reference statement

> Successful reconstruction does **not** mean the AI would have made the
> discovery. The benchmark measures the ability to connect scientific dots
> given pre-cutoff evidence.

## 8. Evaluation framework

`backend/evaluation/metrics.py` exposes independent metrics:

- `retrieval_accuracy` — recall against a provided gold identifier set
- `citation_accuracy` — does the cited quote actually appear in the abstract?
- `graph_integrity` — orphan edges, edges without any supporting paper
- `connection_integrity` — multi-hop connections referencing missing edges
- `hypothesis_quality` — presence of a testable prediction, suggested
  experiment, evidence-chain length, critique scores

These are deliberately **not** combined into a single "AI scientific accuracy"
number.

## 9. Scientific-integrity disclaimer

> These hypotheses are AI-generated research suggestions based on the
> retrieved literature. They are not experimentally validated scientific
> conclusions and require expert review and experimental testing.

The engine must never claim medical efficacy, cures, or causal certainty on
the basis of inference alone. If evidence is insufficient the correct answer
is "Insufficient evidence." — not a forced answer.

## 10. Public hackathon demo (Render, free tier)

The repository includes a Docker deployment and Render Blueprint in `Dockerfile`
and `render.yaml`. Connect this GitHub repository to Render as a **Blueprint**
and select branch `usr/reddi-tejaswi/init`. The Blueprint creates one free web
service, builds the React frontend, serves it from FastAPI, and checks
`/api/health`.

Before the first deploy, set these service environment variables in Render:

- `MODEL_NAME`: the exact model ID from Token Factory.
- `MODEL_API_KEY`: the Token Factory API key. Enter it in Render's Environment
  page as a secret; never put it in GitHub, `render.yaml`, or the frontend.

`MODEL_BASE_URL` is set in the Blueprint. The public demo enables per-IP
request throttling and limits each AI investigation to four unique papers.
The answer verdict and summary are generated from the retrieved abstracts and
validated findings; with AI disabled, API-only search shows papers but does not
invent a yes/no answer.
Keep the Render service on the Free plan. Free services sleep after 15 minutes
without requests and may take about a minute to wake. Render's free plan has
usage limits; if a payment method is attached, set a workspace spend limit to
avoid charges beyond included usage. Nebius model requests use Token Factory
credits separately.

The local `.env` is excluded by both `.gitignore` and `.dockerignore`. The
deployment image runs as a non-root user and does not copy local secrets or
retrieval caches.
