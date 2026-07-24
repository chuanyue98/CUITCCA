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
