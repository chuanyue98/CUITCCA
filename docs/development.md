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
