# Backend Robustness & Retrieval Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two backend correctness/reliability gaps that matter most before this ships — the event loop gets blocked for seconds during file ingestion, and access/feedback data is lost on crash — and replace the naive "try each index, return the first non-empty answer" retrieval strategy with LLM-routed selection across indexes using the summaries the app already computes and stores.

**Architecture:** Three independent, additive changes: (1) wrap the two genuinely expensive synchronous calls in `insert_into_index`/`embeddingQA` (file parsing + embedding) with `asyncio.to_thread` so concurrent requests aren't frozen out during uploads; (2) add a `sqlite3`-backed persistence layer for access stats and feedback, replacing the JSON-file snapshot that only survives a clean shutdown, with a periodic flush so a crash loses at most ~60s of data instead of everything since the last graceful stop; (3) replace `MultiIndexQueryEngine`'s serial "first non-empty wins" scan with LlamaIndex's `RouterQueryEngine`, using the already-built-but-unused `generate_query_engine_tools()` helper in `utils/llama.py`, keeping `MultiIndexQueryEngine` only as the explicit zero-index fallback.

**Tech Stack:** Python 3.12 `asyncio.to_thread`, stdlib `sqlite3` (no new dependency), LlamaIndex `RouterQueryEngine` + `LLMSingleSelector` (already available via `llama-index-core`, already a project dependency).

## Global Constraints

- No new third-party dependency for persistence — use stdlib `sqlite3`, not SQLAlchemy or an ORM (matches the project's otherwise dependency-light backend).
- Do not add a new embedding/reranking model — deferred; see Task 3's "Non-goal" note.
- Every change must keep `uv run pytest tests/ -v --cov=backend/app` green, and `uv run ruff check backend/ tests/` / `uv run mypy backend/app/ tests/ --ignore-missing-imports` clean, matching `.github/workflows/ci.yml`.
- Keep `/index/*` and `/graph/*` route signatures unchanged — this plan is internal implementation, not API surface.

---

## File Structure

- Modify: `backend/app/handlers/index_crud.py` — `insert_into_index`, `embeddingQA` offload blocking calls to a thread.
- Create: `backend/app/utils/db.py` — SQLite schema, connection helper, stats + feedback read/write functions.
- Modify: `backend/app/configs/load_env.py` — add `DB_PATH` env-driven path.
- Modify: `backend/app/main.py` — periodic flush task in `lifespan`, load initial stats from SQLite instead of JSON.
- Modify: `backend/app/utils/file.py` — `save_feedback_to_file` becomes a thin SQLite-backed `save_feedback`.
- Modify: `backend/app/router/manage.py` — `create_feedback` calls the renamed function; add `GET /manage/feedback`.
- Modify: `backend/app/models/response.py` — add `FeedbackEntry`/`FeedbackListResponse` models for the new endpoint.
- Modify: `backend/app/utils/llama.py` — `generate_query_engine_tools` gains `similarity_top_k` and reuses existing `streaming` handling.
- Modify: `backend/app/handlers/graph_builder.py` — `compose_graph_query_engine`/`compose_graph_chat_egine` build a `RouterQueryEngine` when 1+ indexes exist.
- Test: `tests/test_index_dep.py` or new `tests/test_index_crud_async.py` — assert blocking calls go through `asyncio.to_thread`.
- Test: new `tests/test_db.py` — SQLite layer.
- Test: `tests/test_file_utils.py` — update for renamed feedback function.
- Test: `tests/test_llama_handler.py` — update for `generate_query_engine_tools` signature.
- Test: `tests/test_graph_router.py` — add router-engine composition coverage.

---

### Task 1: Offload blocking file-parse/embedding calls to a thread

**Files:**
- Modify: `backend/app/handlers/index_crud.py:55-86`
- Test: new `tests/test_index_crud_async.py`

**Interfaces:**
- Consumes: `utils.llama.get_nodes_from_file(path) -> list[BaseNode]` (unchanged signature), `VectorStoreIndex.insert_nodes(nodes)` (unchanged, third-party).
- Produces: `insert_into_index(index, doc_file_path, skip_summary=False)` and `embeddingQA(index, qa_pairs, id=None)` keep their existing signatures and call sites in `backend/app/router/index.py` — no caller changes needed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_index_crud_async.py`:

```python
import asyncio
from unittest.mock import MagicMock, patch

import pytest

import tests._pathsetup  # noqa: F401
from handlers import index_crud


class FakeIndex:
    def __init__(self):
        self.index_id = 'idx-async-test'
        self.summary = ''
        self.inserted = []

    def insert_nodes(self, nodes):
        self.inserted.extend(nodes)


@pytest.mark.asyncio
async def test_insert_into_index_offloads_parsing_and_embedding():
    index = FakeIndex()
    fake_nodes = [MagicMock()]

    with patch('utils.llama.get_nodes_from_file', return_value=fake_nodes) as mock_get_nodes, \
         patch('asyncio.to_thread', wraps=asyncio.to_thread) as mock_to_thread, \
         patch.object(index_crud, 'summary_index', new=None, create=True):
        # summary skipped so we only assert the parse+insert offload
        await index_crud.insert_into_index(index, '/fake/path.txt', skip_summary=True)

    mock_get_nodes.assert_called_once_with('/fake/path.txt')
    assert index.inserted == fake_nodes
    # both the parse call and the insert_nodes call must go through asyncio.to_thread
    assert mock_to_thread.call_count >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_index_crud_async.py -v`
Expected: FAIL — `mock_to_thread.call_count` is 0 because the current implementation calls `get_nodes_from_file` and `index.insert_nodes` directly on the event loop.

- [ ] **Step 3: Implement**

In `backend/app/handlers/index_crud.py`, replace `insert_into_index` and `embeddingQA` (lines 55-86):

```python
async def insert_into_index(index: VectorStoreIndex, doc_file_path: str, skip_summary: bool = False):
    from handlers.graph_builder import summary_index
    from utils.llama import get_nodes_from_file

    nodes = await asyncio.to_thread(get_nodes_from_file, doc_file_path)

    lock = await _get_index_lock(index.index_id)
    async with lock:
        await asyncio.to_thread(index.insert_nodes, nodes)
        if not skip_summary:
            index.summary = await summary_index(index)
            _save_summary(index)


async def embeddingQA(index: VectorStoreIndex, qa_pairs: list, id: str | None = None):
    if id is None:
        id = str(uuid.uuid4())

    docs = []
    for i in range(0, len(qa_pairs), 2):
        q = qa_pairs[i]
        if i + 1 < len(qa_pairs):
            a = qa_pairs[i + 1]
            doc_id = f"{id}_{i//2}"
            doc = Document(text=f"{q} {a}", id_=doc_id)
            customer_logger.info(f"{doc.text}")
            docs.append(doc)

    lock = await _get_index_lock(index.index_id)
    async with lock:
        await asyncio.to_thread(index.insert_nodes, docs)
        _save_summary(index)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_index_crud_async.py -v`
Expected: PASS.

Run: `uv run pytest tests/ -v --cov=backend/app` to confirm no regressions (existing `tests/test_index_dep.py`, `tests/test_index_router.py`, `tests/test_upload_file_async_io.py` exercise `insert_into_index`/`embeddingQA` through mocks and must still pass since the public signatures are unchanged).

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/index_crud.py tests/test_index_crud_async.py
git commit -m "fix: offload blocking file parse and embedding calls off the event loop"
```

---

### Task 2: SQLite-backed access stats and feedback persistence

**Files:**
- Create: `backend/app/utils/db.py`
- Modify: `backend/app/configs/load_env.py:1-62`
- Modify: `backend/app/main.py:34-62`
- Modify: `backend/app/utils/file.py:1-42`
- Modify: `backend/app/router/manage.py:1-38`
- Modify: `backend/app/models/response.py:1-45`
- Test: new `tests/test_db.py`
- Test: `tests/test_file_utils.py:70-102`

**Interfaces:**
- Produces: `db.init_db(path) -> None`, `db.record_visit(client_ip: str, endpoint: str) -> None`, `db.flush_stats(stats: dict) -> None`, `db.load_stats() -> dict`, `db.save_feedback(client_ip: str, email: str | None, message: str) -> None`, `db.list_feedback(limit: int = 100) -> list[dict]`.
- Consumes: `configs.load_env.DB_PATH: str` (new env-driven path, same pattern as `chroma_db_path`).

- [ ] **Step 1: Add `DB_PATH` to `load_env.py`**

In `backend/app/configs/load_env.py`, add `db_path = ''` to the module-level declarations (line 19, next to `chroma_db_path = ''`), add it to the `global` statement in `reload_env_variables` (line 26-27), and inside the function body (after the `chroma_db_path` assignment around line 40) add:

```python
    db_path = os.environ.get('DB_PATH', '../../data/app.db')
```

and after the `chroma_db_path = os.path.join(PROJECT_ROOT, chroma_db_path)` line (line 48):

```python
    db_path = os.path.join(PROJECT_ROOT, db_path)
```

- [ ] **Step 2: Write the failing test for the DB layer**

Create `tests/test_db.py`:

```python
import os
import tempfile
import unittest

import tests._pathsetup  # noqa: F401
from utils import db


class DbTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmpdir.name, 'test.db')
        db.init_db(self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_init_db_creates_tables(self):
        conn = db._connect(self.db_path)
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        self.assertTrue({'access_stats', 'ip_visits', 'endpoint_visits', 'feedback'}.issubset(tables))

    def test_flush_and_load_stats_roundtrip(self):
        stats = {
            'total_visits': 5,
            'user_visits': {'1.2.3.4': 3, '5.6.7.8': 2},
            'endpoint_visits': {'/graph/query': 4, '/': 1},
        }
        db.flush_stats(self.db_path, stats)
        loaded = db.load_stats(self.db_path)
        self.assertEqual(loaded['total_visits'], 5)
        self.assertEqual(loaded['user_visits']['1.2.3.4'], 3)
        self.assertEqual(loaded['endpoint_visits']['/graph/query'], 4)

    def test_save_and_list_feedback(self):
        db.save_feedback(self.db_path, '192.168.1.1', 'a@b.com', 'hello world')
        db.save_feedback(self.db_path, '192.168.1.2', None, 'no email here')
        entries = db.list_feedback(self.db_path, limit=10)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['message'], 'no email here')  # most recent first
        self.assertIsNone(entries[0]['email'])
        self.assertEqual(entries[1]['client_ip'], '192.168.1.1')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.db'`.

- [ ] **Step 4: Implement `backend/app/utils/db.py`**

```python
import sqlite3
from contextlib import closing

_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_stats (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ip_visits (
    ip TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS endpoint_visits (
    endpoint TEXT PRIMARY KEY,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    client_ip TEXT NOT NULL,
    email TEXT,
    message TEXT NOT NULL
);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    with closing(_connect(db_path)) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


def flush_stats(db_path: str, stats: dict) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO access_stats (key, value) VALUES ('total_visits', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (stats.get('total_visits', 0),),
        )
        for ip, count in dict(stats.get('user_visits', {})).items():
            conn.execute(
                "INSERT INTO ip_visits (ip, count) VALUES (?, ?) "
                "ON CONFLICT(ip) DO UPDATE SET count = excluded.count",
                (ip, count),
            )
        for endpoint, count in dict(stats.get('endpoint_visits', {})).items():
            conn.execute(
                "INSERT INTO endpoint_visits (endpoint, count) VALUES (?, ?) "
                "ON CONFLICT(endpoint) DO UPDATE SET count = excluded.count",
                (endpoint, count),
            )
        conn.commit()


def load_stats(db_path: str) -> dict:
    with closing(_connect(db_path)) as conn:
        total_row = conn.execute(
            "SELECT value FROM access_stats WHERE key = 'total_visits'"
        ).fetchone()
        total_visits = total_row['value'] if total_row else 0
        user_visits = {
            row['ip']: row['count']
            for row in conn.execute("SELECT ip, count FROM ip_visits").fetchall()
        }
        endpoint_visits = {
            row['endpoint']: row['count']
            for row in conn.execute("SELECT endpoint, count FROM endpoint_visits").fetchall()
        }
    return {
        'total_visits': total_visits,
        'user_visits': user_visits,
        'endpoint_visits': endpoint_visits,
    }


def save_feedback(db_path: str, client_ip: str, email: str | None, message: str) -> None:
    with closing(_connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO feedback (client_ip, email, message) VALUES (?, ?, ?)",
            (client_ip, email, message),
        )
        conn.commit()


def list_feedback(db_path: str, limit: int = 100) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT created_at, client_ip, email, message FROM feedback "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 6: Wire periodic flush + startup load into `main.py`**

In `backend/app/main.py`, add the import (near the top, with the other `configs.load_env` import block):

```python
from configs.load_env import (
    COOKIE_MAX_AGE,
    COOKIE_SECURE,
    LOAD_PATH,
    SAVE_PATH,
    access_stats_path,
    chroma_db_path,
    db_path,
    reload_env_variables,
)
from utils import db as stats_db
```

Replace the `lifespan` function body (lines 34-61) — swap the JSON `open()`/`json.load` startup block and the shutdown `json.dump` block for SQLite equivalents, and add a background flush loop:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    reload_env_variables()
    init_settings()
    await loadAllIndexes()
    for directory in [SAVE_PATH, LOAD_PATH, chroma_db_path]:
        if not os.path.exists(directory):
            os.makedirs(directory)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    await asyncio.to_thread(stats_db.init_db, db_path)

    loaded = await asyncio.to_thread(stats_db.load_stats, db_path)
    _mgmt_access_stats["total_visits"] = loaded["total_visits"]
    _mgmt_access_stats["user_visits"] = defaultdict(int, loaded["user_visits"])
    _mgmt_access_stats["endpoint_visits"] = defaultdict(int, loaded["endpoint_visits"])
    _mgmt_access_stats["ip_count"] = len(_mgmt_access_stats["user_visits"])

    async def _periodic_flush():
        while True:
            await asyncio.sleep(60)
            async with access_stats_lock:
                snapshot = {
                    "total_visits": _mgmt_access_stats["total_visits"],
                    "user_visits": dict(_mgmt_access_stats["user_visits"]),
                    "endpoint_visits": dict(_mgmt_access_stats["endpoint_visits"]),
                }
            await asyncio.to_thread(stats_db.flush_stats, db_path, snapshot)

    flush_task = asyncio.create_task(_periodic_flush())

    yield

    flush_task.cancel()
    async with access_stats_lock:
        final_snapshot = {
            "total_visits": _mgmt_access_stats["total_visits"],
            "user_visits": dict(_mgmt_access_stats["user_visits"]),
            "endpoint_visits": dict(_mgmt_access_stats["endpoint_visits"]),
        }
    await asyncio.to_thread(stats_db.flush_stats, db_path, final_snapshot)
```

Note `access_stats_lock` is defined a few lines below the original `lifespan` (line 71); move its definition (`access_stats_lock = asyncio.Lock()`) to just above the `app = FastAPI(lifespan=lifespan)` line so `lifespan` can reference it — Python resolves the name at call time, not definition time, but `asyncio.Lock()` must exist as a module attribute before `lifespan` is ever invoked, so simplest is to define it directly above `app = FastAPI(...)`, replacing its old location. Also remove the now-unused `import json` if nothing else in the file uses it (grep the file first — `json.dumps`/`json.load` elsewhere would keep the import necessary).

- [ ] **Step 7: Rename and rewire feedback persistence**

In `backend/app/utils/file.py`, replace `save_feedback_to_file` (lines 32-41) with:

```python
async def save_feedback(client_ip: str, feedback: Feedback):
    from configs.load_env import db_path
    from utils import db
    await asyncio.to_thread(db.save_feedback, db_path, client_ip, feedback.email, feedback.message)
```

Remove the now-unused `from datetime import datetime` import if nothing else in the file uses `datetime` (grep first).

In `backend/app/router/manage.py`, update the import (`from utils.file import save_feedback_to_file` → `from utils.file import save_feedback`) and the call site inside `create_feedback` (line 37): `await save_feedback_to_file(feedback, client_ip)` → `await save_feedback(client_ip, feedback)`.

- [ ] **Step 8: Add a feedback-listing endpoint**

In `backend/app/models/response.py`, append:

```python
class FeedbackEntry(BaseModel):
    created_at: str
    client_ip: str
    email: str | None = None
    message: str


class FeedbackListResponse(BaseModel):
    feedback: list[FeedbackEntry]
```

In `backend/app/router/manage.py`, add the import `FeedbackEntry, FeedbackListResponse` to the existing `from models.response import (...)` line, and add a new endpoint after `create_feedback`:

```python
@manage_app.get("/feedback", response_model=FeedbackListResponse, dependencies=[Depends(require_configured_api_key)])
async def get_feedback(limit: int = 100):
    """列出最近的用户反馈"""
    from configs.load_env import db_path
    from utils import db
    entries = await asyncio.to_thread(db.list_feedback, db_path, limit)
    return FeedbackListResponse(feedback=entries)
```

- [ ] **Step 9: Update the feedback test for the new signature**

In `tests/test_file_utils.py`, replace the two `@patch('utils.file.FEEDBACK_PATH', '/fake/feedback')` tests (lines 72-102, using the exact surrounding test bodies already in the file) with a single test against the new `save_feedback`:

```python
    def test_save_feedback_persists_to_sqlite(self):
        with patch('utils.file.db.save_feedback') as mock_save, \
             patch('utils.file.db_path', '/fake/app.db'):
            feedback = Feedback(email='a@b.com', message='hello')
            asyncio.run(f.save_feedback('192.168.1.1', feedback))
        mock_save.assert_called_once_with('/fake/app.db', '192.168.1.1', 'a@b.com', 'hello')
```

(Adjust the exact `Feedback(...)` construction/imports to match whatever helper the existing test file already uses at the top — read the file's imports before editing so the patch target module path is exactly right.)

- [ ] **Step 10: Run the full suite**

Run: `uv run pytest tests/ -v --cov=backend/app`
Expected: All tests PASS, including `tests/test_db.py`, `tests/test_main.py`, `tests/test_file_utils.py`, `tests/test_graph_router.py` (unaffected).

- [ ] **Step 11: Update `.gitignore` and commit**

Add `/data/app.db` is already covered by the existing `/data/` ignore rule in `.gitignore` — verify with `git status` that no `data/app.db` file shows as untracked-but-should-be-ignored; if it does, add an explicit line `data/app.db` under the existing `/data/` entry for clarity.

```bash
git add backend/app/utils/db.py backend/app/configs/load_env.py backend/app/main.py \
        backend/app/utils/file.py backend/app/router/manage.py backend/app/models/response.py \
        tests/test_db.py tests/test_file_utils.py
git commit -m "feat: persist access stats and feedback to SQLite with periodic flush"
```

---

### Task 3: Router-based multi-index retrieval

**Non-goal:** Adding a cross-encoder reranker (e.g. `bge-reranker-v2-m3`) was considered and deliberately deferred — it would add a second multi-hundred-MB model download and extra CPU latency per query, which is a real cost for a "not in production yet" project. This task gets the bigger, cheaper win first: replacing "first non-empty answer wins" with LLM-routed selection across the summaries the app already maintains.

**Files:**
- Modify: `backend/app/utils/llama.py:95-105`
- Modify: `backend/app/handlers/graph_builder.py:61-86`
- Test: `tests/test_llama_handler.py` (update `generate_query_engine_tools` coverage)
- Test: `tests/test_graph_router.py` (extend router-composition coverage)

**Interfaces:**
- Consumes: `index.summary: str` (already populated and persisted via `_save_summary`, see `backend/app/handlers/index_crud.py:158-161`).
- Produces: `compose_graph_query_engine(streaming: bool = False) -> BaseQueryEngine` and `compose_graph_chat_egine() -> BaseChatEngine` keep their exact existing signatures — callers in `backend/app/router/graph.py` and `backend/app/router/index.py` need no changes.

- [ ] **Step 1: Extend `generate_query_engine_tools` with an explicit top_k**

In `backend/app/utils/llama.py`, replace `generate_query_engine_tools` (lines 95-105):

```python
def generate_query_engine_tools(
    indexes: list[BaseIndex], streaming: bool = False, similarity_top_k: int = 5
) -> list[QueryEngineTool]:
    query_engine_tools = []
    for index in indexes:
        query_engine = index.as_query_engine(
            streaming=streaming,
            text_qa_template=Prompts.QA_PROMPT.value,
            refine_template=Prompts.REFINE_PROMPT.value,
            similarity_top_k=similarity_top_k,
        )
        description = index.summary or f"知识库索引: {index.index_id}"
        tool = QueryEngineTool.from_defaults(query_engine=query_engine, description=description)
        query_engine_tools.append(tool)

    return query_engine_tools
```

(The `description = index.summary or ...` fallback matters: `RouterQueryEngine`'s `LLMSingleSelector` picks a tool based on its description, and an empty string gives the selector nothing to reason about for freshly created indexes that haven't been summarized yet.)

- [ ] **Step 2: Write the failing test for router composition**

In `tests/test_graph_router.py`, add near the top of `GraphRouterTest` (after `setUp`/`tearDown`, before the `/graph/create` section):

```python
    # ── router-based multi-index composition ───────────────────────

    def test_compose_query_engine_uses_router_with_indexes(self):
        import handlers.graph_builder as gb
        fake_index = MagicMock()
        fake_index.index_id = 'idx1'
        fake_index.summary = 'campus dorm rules'
        fake_index.as_query_engine.return_value = MagicMock()

        with patch.object(gb, 'indexes', [fake_index]):
            gb.invalidate_query_engine_cache()
            engine = gb.compose_graph_query_engine()

        from llama_index.core.query_engine import RouterQueryEngine
        self.assertIsInstance(engine, RouterQueryEngine)
        gb.invalidate_query_engine_cache()

    def test_compose_query_engine_falls_back_with_no_indexes(self):
        import handlers.graph_builder as gb
        with patch.object(gb, 'indexes', []):
            gb.invalidate_query_engine_cache()
            engine = gb.compose_graph_query_engine()

        self.assertIsInstance(engine, gb.MultiIndexQueryEngine)
        gb.invalidate_query_engine_cache()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_router.py -k compose_query_engine -v`
Expected: FAIL — `compose_graph_query_engine()` currently always returns a `MultiIndexQueryEngine`, never a `RouterQueryEngine`.

- [ ] **Step 4: Implement the router composition**

In `backend/app/handlers/graph_builder.py`, add the import at the top (with the other `llama_index.core` imports):

```python
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.selectors import LLMSingleSelector
from utils.llama import generate_query_engine_tools
```

Replace `compose_graph_chat_egine` and `compose_graph_query_engine` (lines 64-86):

```python
def _build_query_engine(streaming: bool) -> BaseQueryEngine:
    indexes_snapshot = list(indexes)
    if not indexes_snapshot:
        return MultiIndexQueryEngine(indexes_snapshot=[], streaming=streaming)
    if len(indexes_snapshot) == 1:
        # 单索引无需路由选择，直接查询避免额外的 LLM 选择调用
        return indexes_snapshot[0].as_query_engine(
            streaming=streaming,
            text_qa_template=Prompts.QA_PROMPT.value,
            refine_template=Prompts.REFINE_PROMPT.value,
            similarity_top_k=5,
        )
    tools = generate_query_engine_tools(indexes_snapshot, streaming=streaming, similarity_top_k=5)
    return RouterQueryEngine.from_defaults(
        query_engine_tools=tools,
        selector=LLMSingleSelector.from_defaults(),
        select_multi=False,
        verbose=VERBOSE,
    )


def compose_graph_chat_egine() -> BaseChatEngine:
    query_engine = _build_query_engine(streaming=True)

    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=query_engine,
        condense_question_prompt=Prompts.CONDENSE_QUESTION_PROMPT.value,
        verbose=VERBOSE,
    )

    return chat_engine


def compose_graph_query_engine(streaming: bool = False) -> BaseQueryEngine:
    global _query_engine_cache
    if _query_engine_cache is None:
        _query_engine_cache = _build_query_engine(streaming)
    return _query_engine_cache
```

`select_multi=False` (single-index selection per query, not multi-index fan-out) is the deliberate choice here: `select_multi=True` would combine answers from several indexes via an extra summarization LLM call per query, doubling latency for a benefit that matters only when a single question genuinely spans multiple knowledge bases — uncommon for a campus FAQ bot where indexes are typically topic-partitioned (e.g. one per department). Leave a comment noting this trade-off can be revisited if multi-topic queries turn out to be common.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_router.py -v`
Expected: All PASS, including the two new tests. Note `test_query_router` (the existing test at the bottom of the file, testing `/graph/query_router`) patches `handlers.graph_builder.MultiIndexQueryEngine` directly and is untouched by this change since that endpoint still constructs `MultiIndexQueryEngine` explicitly — confirm it still passes.

- [ ] **Step 6: Update `tests/test_llama_handler.py` for the new `generate_query_engine_tools` signature**

Open `tests/test_llama_handler.py`, find the existing test(s) covering `generate_query_engine_tools`, and add an assertion that `similarity_top_k=5` (the new default) is passed through to `as_query_engine`. Read the existing test's exact mock-assertion style first (it likely already asserts on `as_query_engine.assert_called_once_with(...)` or inspects `call_args`) and extend that same assertion to include `similarity_top_k=5`, matching the file's established pattern rather than introducing a new one.

- [ ] **Step 7: Run the full suite and static checks**

```bash
uv run pytest tests/ -v --cov=backend/app
uv run ruff check backend/ tests/
uv run mypy backend/app/ tests/ --ignore-missing-imports
```

Expected: all green.

- [ ] **Step 8: Manual verification with a real (or locally-configured) LLM**

With at least two indexes created via `/index/create` and populated via `/index/{name}/uploadFile`, and each given a distinct summary via `/index/{name}/generate_summary`, ask a question via the chat UI that clearly belongs to one index's topic and confirm the answer draws from the correct index (check `/graph/query_sources` after the query to see which `doc_id`s were cited).

- [ ] **Step 9: Commit**

```bash
git add backend/app/utils/llama.py backend/app/handlers/graph_builder.py \
        tests/test_llama_handler.py tests/test_graph_router.py
git commit -m "feat: route queries across indexes with LLMSingleSelector instead of first-non-empty scan"
```

---

## Self-Review

**Spec coverage:**
- Item #3 (retrieval quality) → Task 3 (`RouterQueryEngine` + `LLMSingleSelector`, raised `similarity_top_k`). Reranker explicitly deferred with rationale. ✓
- Item #5 (async blocking) → Task 1 (`asyncio.to_thread` around file parsing + embedding). ✓
- Item #6 (durable stats/feedback persistence) → Task 2 (SQLite + periodic flush + feedback table + listing endpoint). ✓

**Placeholder scan:** No TBD/TODO; Step 6 of Task 2 and Step 6 of Task 3 ask the implementer to match an existing file's style rather than inventing one from scratch — this is intentional (the exact current content of those test files should be read at execution time, not guessed at plan-writing time) and both give a concrete, verifiable expected outcome, not a vague instruction.

**Type/name consistency:** `db_path` (lowercase, matches `chroma_db_path`'s naming convention in `load_env.py`) is used consistently across `main.py`, `utils/file.py`, `router/manage.py`. `save_feedback` (renamed from `save_feedback_to_file`) is updated at its one call site in `router/manage.py`. `_build_query_engine` is a new private helper introduced and consumed only within `graph_builder.py` by the two public functions that already existed with unchanged signatures.
