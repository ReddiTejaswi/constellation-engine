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

- Python 3.12
- Node 20+
- An OpenAI-compatible chat completions endpoint. For the hackathon build, use
  Nebius Token Factory with an NVIDIA open model; other compatible endpoints
  can be used for local development.

### Backend

```bash
# Linux / macOS
cp .env.example .env
# Edit .env and provide at least MODEL_NAME, MODEL_BASE_URL, MODEL_API_KEY.

python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m backend.server
# → serves on http://${HOST:-0.0.0.0}:${PORT:-8000}
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Edit .env, then start the backend:
.\.venv\Scripts\python.exe -m backend.server
```

Set `MODEL_NAME`, `MODEL_BASE_URL`, and `MODEL_API_KEY` in the local `.env`
file before starting the server.

### Frontend

```bash
cd frontend
npm ci
npm run build            # production bundle, served by FastAPI at /
# or during development:
npm run dev              # http://localhost:5173, proxies /api → :8000
```

If `frontend/dist` exists, the FastAPI app serves it from `/` directly, so a
single process is enough in production.

### Tests

```bash
# Linux / macOS
.venv/bin/python -m pytest -q
```

On Windows PowerShell: `\.venv\Scripts\python.exe -m pytest -q`.

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

## 10. Hackathon model integration

For the hackathon deployment, the backend makes runtime chat-completions calls
to Nebius Token Factory using an NVIDIA open model selected through
`MODEL_NAME`. The Token Factory URL and model credentials are configured on the
server; the API key is never exposed to the frontend. AI-generated answers,
connections, and hypotheses are grounded in retrieved papers and remain
research suggestions that require expert review.

## 11. Contributors

- [Reddi Tejaswi Rasetty](https://github.com/ReddiTejaswi)
- [gandharvam](https://github.com/gandharvam)

## 12. License

This project is licensed under the [MIT License](LICENSE).
