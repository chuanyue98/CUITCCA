# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-07-24

### Added
- Frontend modernization: Vite + TypeScript dev/build pipeline with hot module replacement.
- Type-safe API interfaces in `frontend/src/types/api.ts`.
- Production build step outputting to `backend/app/static/` for FastAPI static serving.
- Makefile targets: `frontend-install`, `frontend-dev`, `frontend-build`.

### Changed
- Frontend source migrated from plain JS to TypeScript (`sidebar.ts`, `chat.ts`, `manage.ts`, `feedback.ts`, `feed_back.ts`).
- Inline `onclick`/`oninput` handlers replaced with `addEventListener` bindings for ES module compatibility.

### Fixed
- XLSX file parsing support via explicit `openpyxl` usage in `utils/file.py`.
- PromptTemplate parameter error in `router/index.py` (was passing object instead of template string).
- Upload file storage now uses `index_id` subdirectory with failure rollback.
- `insert_docs` now uses index-level lock and invalidates hybrid retriever cache.
- `access_stats_lock` moved to `dependencies/manage.py` to resolve circular import.
- Missing `get_client_ip` function added to `utils/security.py`.

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
