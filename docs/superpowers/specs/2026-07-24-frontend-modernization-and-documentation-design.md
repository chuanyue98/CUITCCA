# Frontend Modernization & Documentation

**Date**: 2026-07-24
**Status**: Draft
**Scope**: Frontend modernization (Vite + TypeScript) + documentation (CHANGELOG, API docs, deployment, troubleshooting, development guide)

---

## 1. Goals

- Upgrade the frontend from static HTML/CSS/JS to a typed, hot-reloadable dev environment with a proper build step, while keeping runtime behavior unchanged.
- Add user-facing and operator-facing documentation so the project is usable and deployable without reading source code.

## 2. Frontend Modernization

### 2.1 Constraints

- Do not rewrite business logic in chat.js / manage.js / feedback.js / sidebar.js.
- Keep the page structure and CSS architecture the same.
- Playwright e2e tests must continue to pass after the build tooling is added.
- The FastAPI app must continue serving the frontend with no extra runtime dependency.

### 2.2 Approach

Adopt **Vite + TypeScript** as a dev/build layer on top of the existing static files.

| Step | Action |
|---|---|
| 1 | Add `frontend/package.json` with Vite, TypeScript, and `@types/node`. |
| 2 | Add `frontend/vite.config.ts` that proxies `/api` to the FastAPI backend and outputs built assets to `backend/app/static/`. |
| 3 | Rename `frontend/*.js` to `*.ts` and add a minimal `frontend/src/types/api.ts` that mirrors the backend Pydantic response models used by the pages. |
| 4 | Add `frontend/tsconfig.json` with strict mode enabled. |
| 5 | Add a Vite multi-page entry for each existing page (`index.html`, `manage.html`, `use_function.html`, `feed_back.html`); each becomes an independent Vite entry with its own JS/TS bundle. |
| 6 | Update `main.py` to serve `backend/app/static/` in production; dev mode uses Vite dev server directly. |
| 7 | Remove `tests/playwright/package.json` and its committed `node_modules` history from git to avoid polluting the repo. |
| 8 | Add a `frontend/` section to `Makefile` (`frontend-install`, `frontend-dev`, `frontend-build`). |

### 2.3 Non-goals

- Do not migrate to React or any component framework.
- Do not change the backend API shape or routing.

## 3. Documentation

### 3.1 CHANGELOG.md

Record notable changes at the root. Start with a retroactive summary covering:
- v0.1.0: Initial RAG + index management + multi-turn chat.
- v0.2.0: QAWorkflow, hybrid retrieval (BM25 + dense RRF), conditional rerank, incremental ingestion with sha256 dedup, OpenTelemetry observability.
Mark each entry with "Added / Changed / Fixed / Breaking".

### 3.2 docs/api.md

Document all user-facing endpoints from `router/` with:
- Path, method, required auth.
- Request body / query params.
- Response body with examples.
- Notes on streaming endpoints (`/graph/chat_stream`, `/graph/query_stream`).

Reference FastAPI's auto-generated `/docs` and `/redoc` as the live source of truth.

### 3.3 docs/deployment.md

Cover:
- systemd service unit example.
- Environment variable reference (from `.env.example`).
- Nginx reverse proxy config.
- Running with `uvicorn` behind a process manager.
- Chroma persistence directory ownership and backup.
- Production hardening notes (rate limiting, CORS allowlist, TLS termination).

### 3.4 docs/troubleshooting.md

Cover common failure modes:
- Embedding model download fails on first run (disk / network).
- Reranker model memory pressure.
- "No API key configured" errors and how to set `OPENAI_API_KEY`.
- Index corruption recovery (delete and re-ingest).
- Log locations and how to increase verbosity.

### 3.5 docs/development.md

Cover:
- Local setup with `uv sync`.
- Running backend (`make dev`).
- Running frontend dev server (`make frontend-dev`).
- Running tests (`make test`, `make lint`, `make typecheck`, `make security`).
- Running evals (`python evals/run_hybrid_eval.py` etc.).
- Playwright e2e tests and when to skip them.

## 4. Implementation Order

1. Frontend Vite + TS scaffolding and build pipeline.
2. CHANGELOG.md.
3. API docs.
4. Deployment + troubleshooting + development docs.

## 5. Verification

- `make lint`, `make typecheck`, `make test` must remain green after frontend file renames.
- Playwright tests must pass in CI.
- Built assets must be served correctly by FastAPI in production mode.
