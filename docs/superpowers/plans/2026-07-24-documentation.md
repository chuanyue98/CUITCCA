# Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user-facing and operator-facing documentation so the project is usable and deployable without reading source code.

**Architecture:** Markdown documents in `docs/` covering changelog, API reference, deployment, troubleshooting, and development guide. CHANGELOG.md at repo root.

**Tech Stack:** Markdown

## Global Constraints

- Documentation must be accurate to the current codebase (verify against actual endpoints, env vars, and commands).
- Keep Chinese language consistent with existing README tone.
- Reference FastAPI's auto-generated `/docs` and `/redoc` as the live API source of truth.

---

### Task 1: Write CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

**Interfaces:**
- Consumes: git log, README.md, `.env.example`
- Produces: Version history document

- [ ] **Step 1: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-18

### Added
- QAWorkflow: migrated all chat endpoints to LlamaIndex Workflow primitives (`condense_question -> retrieve -> synthesize`) with streaming support.
- Hybrid retrieval: BM25 (jieba + bm25s) + dense vector RRF fusion, default-enabled via `HYBRID_RETRIEVAL_ENABLED`.
- Conditional cross-encoder rerank (bge-reranker-v2-m3), default-enabled via `RERANK_ENABLED`, with eval-validated parameters (`recall_k=20`, `top_n=5`, `score_threshold=0.75`).
- Incremental ingestion pipeline with sha256 content dedup and conflict resolution (same-directory update vs cross-directory conflict).
- OpenTelemetry observability (OpenInference + OTLP), env-gated via `OBSERVABILITY_ENABLED`.
- Hybrid retrieval eval framework (`evals/run_hybrid_eval.py`) with A/B/C baselines.
- Rerank A/B eval (`evals/run_rerank_eval.py`) and workflow retrieval eval (`evals/run_workflow_retrieval_eval.py`).

### Changed
- Retrieval layer unified through `build_retriever_for_index()` entry point.
- `handlers/graph_builder.py` reduced to `summary_index()` only; legacy `CondenseQuestionChatEngine`/`RouterQueryEngine` removed.
- Rate limiting refined to cover only LLM query endpoints.

### Fixed
- P0 CI quality gate: fixed `ConditionalRerankPostprocessor` lazy-loading race condition.
- docx/xlsx upload regression: added `docx2txt` and `openpyxl` as explicit dependencies.

## [0.1.0] - 2025-07-10

### Added
- Initial RAG Q&A system with LlamaIndex + Chroma vector store.
- Multi-turn chat with streaming token output (`/graph/chat_stream`).
- Markdown rendering with `marked.js` + DOMPurify, with expandable citation sources.
- Knowledge base management: create/delete indexes, upload documents (PDF/DOCX/TXT/MD/CSV/XLSX), add/remove nodes.
- QA generation from documents (`/index/{name}/upload_file_by_QA`).
- Graph query endpoints (`/graph/query`, `/graph/query_stream`).
- Conversation history persistence in `localStorage`.
- Dark mode via `prefers-color-scheme`.
- Feedback collection page (`/manage/feedback`).
- Usage guide page.
- CI pipeline: lint (`ruff`), typecheck (`mypy`), test (`pytest` + coverage gate 90%), security (`pip-audit`, `bandit`).
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG.md with v0.1.0 and v0.2.0 history"
```

---

### Task 2: Write `docs/api.md`

**Files:**
- Create: `docs/api.md`

**Interfaces:**
- Consumes: `backend/app/router/` (all routers), `backend/app/models/response.py`
- Produces: API reference document

- [ ] **Step 1: Read all router files and models to extract endpoint signatures**

Read:
- `backend/app/router/graph.py`
- `backend/app/router/index.py`
- `backend/app/router/response.py`
- `backend/app/router/manage.py`
- `backend/app/models/response.py`

- [ ] **Step 2: Write `docs/api.md`**

```markdown
# API Reference

Base URL: `/`

All endpoints are prefixed as shown. The FastAPI app also exposes auto-generated interactive docs at `/docs` (Swagger UI) and `/redoc` (ReDoc), which are the live source of truth.

## Chat & Query

### POST /graph/chat_stream
Stream a QA answer for a query using the active conversation context.

**Auth:** None (rate-limited per IP).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required): The user's question.

**Response:** `text/event-stream` (Server-Sent Events)

**Notes:** Real token-level streaming. Abortable via `AbortController`.

### POST /graph/query
Non-streaming QA answer.

**Auth:** None (rate-limited per IP).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required)

**Response:** JSON (`QueryResponse`)

### POST /graph/query_stream
Streaming QA answer without chat context.

**Auth:** None (rate-limited per IP).

**Request:** `application/x-www-form-urlencoded`
- `query` (string, required)

**Response:** `text/event-stream`

### POST /graph/query_sources
Fetch source nodes for the last query.

**Auth:** None.

**Request:** None.

**Response:** JSON
```json
{
  "source_nodes": [
    { "text": "...", "node_id": "...", "doc_id": "..." }
  ]
}
```

### POST /graph/create
Reset the server-side conversation context.

**Auth:** None.

**Request:** None.

**Response:** JSON `{ "status": "ok" }`

### POST /graph/agent
Legacy agent endpoint (deprecated, routes to QAWorkflow).

### POST /graph/query_history
Return conversation history for the current session.

## Index Management

### GET /index/
List all index names.

**Response:** JSON (`IndexListResponse`)

### POST /index/
Create a new index.

**Request:** `application/x-www-form-urlencoded`
- `index_name` (string, required)

**Response:** JSON `{ "status": "success", "index_name": "..." }`

### POST /index/{index_name}/delete
Delete an index and all its data.

**Auth:** API key protected (`CUITCCA_API_KEY`).

**Request:** `application/x-www-form-urlencoded`
- `index_name` (string, required)

### POST /index/{index_name}/uploadFiles
Upload and parse files into the index.

**Auth:** API key protected.

**Request:** `multipart/form-data`
- `files` (file[], required): Supported types: `.txt`, `.pdf`, `.md`, `.csv`, `.xlsx`, `.docx`.

**Response:** JSON (`UploadResponse`)

### POST /index/{index_name}/insertdoc
Insert raw text as a document.

**Auth:** API key protected.

**Request:** `application/x-www-form-urlencoded`
- `text` (string, required)
- `doc_id` (string, optional)

### POST /index/{index_name}/upload_file_by_QA
Generate QA pairs from a file and ingest them.

**Auth:** API key protected.

**Request:** `multipart/form-data`
- `file` (file, required)
- `prompt` (string, optional)

### GET /index/{index_name}/info
List all nodes in an index.

**Auth:** API key protected.

**Response:** JSON `{ "docs": [...] }`

### POST /index/{index_name}/update
Update a node's text content.

**Auth:** API key protected.

**Request:** `application/x-www-form-urlencoded`
- `nodeId` (query string, required)
- `text` (string, required)

### POST /index/{index_name}/deleteNode
Delete a single node.

**Auth:** API key protected.

**Request:** `application/x-www-form-urlencoded`
- `node_id` (query string, required)

### POST /index/{index_name}/deleteDoc
Delete all nodes belonging to a document.

**Auth:** API key protected.

**Request:** `application/x-www-form-urlencoded`
- `doc_id` (query string, required)

### POST /index/{index_name}/get_summary
Get index summary text.

**Auth:** API key protected.

**Response:** JSON `{ "summary": "..." }`

### POST /index/{index_name}/set_summary
Set index summary text.

**Auth:** API key protected.

**Request:** `application/x-www-form-urlencoded`
- `summary` (string, required)

### POST /index/{index_name}/save
Persist index to disk.

**Auth:** API key protected.

**Response:** JSON `{ "status": "ok" }`

## Response Synthesizer

### POST /response/
Synthesize a response using selectable `ResponseMode` and `PromptType`.

**Auth:** API key protected.

**Request:** JSON body with `query`, `index_name`, `response_mode`, `prompt_type`.

See `/docs` for full schema.

## Management

### GET /manage/stats
Return access statistics.

**Auth:** API key protected.

**Response:** JSON (`StatsResponse`)

### POST /manage/feedback
Submit user feedback.

**Auth:** None (but requires valid `email` field).

**Request:** JSON
```json
{
  "email": "user@example.com",
  "message": "反馈内容"
}
```

### POST /manage/env
Update environment variables at runtime (hot-reload).

**Auth:** API key protected.

**Request:** JSON `{ "key": "VARIABLE_NAME", "value": "new_value" }`

## Static Files

### GET /web/
Serves the frontend. In production, built assets are served from `backend/app/static/`. In development, the Vite dev server runs on port 5173 with API proxy.
```

- [ ] **Step 3: Commit**

```bash
git add docs/api.md
git commit -m "docs: add API reference"
```

---

### Task 3: Write `docs/deployment.md`

**Files:**
- Create: `docs/deployment.md`

**Interfaces:**
- Consumes: `backend/.env.example`, `pyproject.toml`, `Makefile`
- Produces: Deployment guide

- [ ] **Step 1: Write `docs/deployment.md`**

```markdown
# Deployment Guide

## Prerequisites

- Python >= 3.12
- `uv` package manager
- OpenAI-compatible API key
- Sufficient disk for Chroma persistence and embedding model cache

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in at least:

```env
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1  # optional
OPENAI_MODEL=sensenova-6.7-flash-lite       # optional
CUITCCA_API_KEY=change-me                   # required for manage endpoints
```

See `.env.example` for the full list (CORS, paths, retrieval tuning, rerank settings).

## Build Frontend

```bash
make frontend-install
make frontend-build
```

This produces production assets in `backend/app/static/`.

## Run with systemd

Create `/etc/systemd/system/cuitcca.service`:

```ini
[Unit]
Description=CUITCCA Campus AI Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/cuitcca
Environment="PATH=/opt/cuitcca/.venv/bin"
ExecStart=/opt/cuitcca/.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8522
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cuitcca
```

## Run with Docker (optional)

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libgomp1 && rm -rf /var/lib/apt/lists/*
COPY . /app
RUN pip install uv && uv sync --frozen
EXPOSE 8522
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8522"]
```

## Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name cuitcca.example.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8522;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Chroma Persistence

Chroma data lives at `CHROMA_DB_PATH` (default: `data/chroma_db`). Back up this directory to preserve indexes. The incremental ingestion pipeline avoids duplicate chunks, but a full re-ingest is possible if corruption occurs.

## Production Hardening

- Set `CORS_ORIGINS` to your real origins (comma-separated).
- Set `COOKIE_SECURE=true` if serving over HTTPS.
- Set a strong `CUITCCA_API_KEY` and keep it secret.
- Tune `RERANK_RECALL_K` / `RERANK_TOP_N` based on latency/quality trade-offs.
- Monitor logs in `log/` and increase verbosity via Python logging config if needed.
```

- [ ] **Step 2: Commit**

```bash
git add docs/deployment.md
git commit -m "docs: add deployment guide"
```

---

### Task 4: Write `docs/troubleshooting.md`

**Files:**
- Create: `docs/troubleshooting.md`

**Interfaces:**
- Consumes: `backend/.env.example`, `backend/app/configs/`
- Produces: Troubleshooting guide

- [ ] **Step 1: Write `docs/troubleshooting.md`**

```markdown
# Troubleshooting

## Embedding model download fails on first run

Symptom: startup hangs or crashes with network errors downloading `BAAI/bge-m3` or similar.

Fix: ensure the host has outbound HTTPS and enough disk (~2 GB for the default embedding model). If the machine has no internet, pre-download the model or mount a cache directory.

## Reranker model memory pressure

Symptom: OOM or sluggish responses after enabling `RERANK_ENABLED`.

Fix: `bge-reranker-v2-m3` is ~2.2 GB. If memory is constrained, set `RERANK_ENABLED=False` or reduce `RERANK_RECALL_K` (default 20).

## "No API key configured"

Symptom: `/manage/*` endpoints return 500 or "API key not configured".

Fix: set `OPENAI_API_KEY` in `backend/.env`. The LLM and embedding clients both require it. Restart the server after editing `.env`.

## Index corruption recovery

Symptom: search returns empty or Chroma throws schema errors.

Fix:
1. Stop the server.
2. Delete or move the Chroma directory (`data/chroma_db` by default).
3. Re-ingest documents via the manage page or `python evals/ingest_corpus.py`.

## Logs

Application logs are written to `log/` (configured in `backend/app/utils/logger.py`). Increase verbosity by adjusting the logger level in code or environment.

## Playwright tests fail after frontend build

Symptom: e2e tests cannot find selectors.

Fix: ensure `make frontend-build` was run and `backend/app/static/` contains the latest assets. Playwright tests should run against the running server on port 8522.
```

- [ ] **Step 2: Commit**

```bash
git add docs/troubleshooting.md
git commit -m "docs: add troubleshooting guide"
```

---

### Task 5: Write `docs/development.md`

**Files:**
- Create: `docs/development.md`

**Interfaces:**
- Consumes: `Makefile`, `pyproject.toml`, `evals/README.md`
- Produces: Developer guide

- [ ] **Step 1: Write `docs/development.md`**

```markdown
# Development Guide

## Local Setup

```bash
git clone https://github.com/ChuanYuei/CUITCCA.git
cd CUITCCA
uv sync
cp backend/.env.example backend/.env
# edit backend/.env and set OPENAI_API_KEY
```

## Run Backend

```bash
make dev
# or
cd backend && uv run python app/main.py
```

Server runs at `http://localhost:8522`.

## Run Frontend (dev mode with hot reload)

```bash
make frontend-install
make frontend-dev
```

Vite runs at `http://localhost:5173` and proxies API requests to the backend.

## Build Frontend (production)

```bash
make frontend-build
```

Assets are written to `backend/app/static/`.

## Tests

```bash
make test          # pytest with coverage
make lint          # ruff
make typecheck     # mypy
make security      # pip-audit + bandit
```

Playwright e2e tests live in `tests/playwright/`. Run them with the server running:

```bash
npx playwright test
```

## Evals

See `evals/README.md` for the full eval framework overview.

Quick start:
```bash
python evals/ingest_corpus.py
python evals/run_hybrid_eval.py
python evals/run_rerank_eval.py
python evals/run_workflow_retrieval_eval.py
```

Eval smoke test (runs in CI):
```bash
uv run pytest tests/test_evals_smoke.py -v
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/development.md
git commit -m "docs: add development guide"
```

---

## Verification Checklist

- [ ] `CHANGELOG.md` is present at repo root and reviewed for accuracy.
- [ ] `docs/api.md`, `docs/deployment.md`, `docs/troubleshooting.md`, `docs/development.md` all exist.
- [ ] `make lint`, `make typecheck`, `make test` still pass.
- [ ] Frontend build pipeline still works (`make frontend-build`).