# DevOps & Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project easy to hand to someone else — a one-command Docker deployment, a Playwright e2e suite that's actually tracked and runs in CI instead of sitting as untracked local artifacts, and removal of the sharpest naming/dead-code rough edges.

**Architecture:** Three independent housekeeping changes: (1) a Dockerfile + docker-compose.yml mirroring the exact launch pattern `backend.bash` already uses (`python backend/app/main.py` from the repo root, which relies on `backend/app` being auto-added to `sys.path`); (2) commit the Playwright suite's source files while gitignoring its generated artifacts, and add a non-blocking CI job that runs it against a live local server; (3) a scoped rename/dead-code pass — fix the `compose_graph_chat_egine` typo repo-wide, and collapse the two near-duplicate "dump index to a text file" functions (`citf` and the unused `convert_index_to_file`) into one clearly-named function.

**Tech Stack:** Docker + docker-compose, GitHub Actions (extending the existing `.github/workflows/ci.yml`), `sed` for the mechanical rename.

## Global Constraints

- **Ordering dependency:** Task 3 (the rename) assumes `docs/superpowers/plans/2026-07-11-chat-experience-overhaul.md` and `docs/superpowers/plans/2026-07-11-backend-robustness-and-retrieval.md` have already landed on the branch. Both of those plans add new call sites and test patches referencing the current (misspelled) `compose_graph_chat_egine` name; run this plan's Task 3 last so the rename sweeps up everything in one pass instead of chasing a moving target.
- Do not attempt to normalize the `{'status': 'error'}` vs `{'status': 'detail'}` response-shape inconsistency across `index.py`/`manage.py`/`graph.py` — `frontend/manage.js` and `frontend/chat.js` branch on these exact string values in several places, and a partial fix risks silently breaking a working UI flow for cosmetic gain. Out of scope for this round.
- No new runtime dependency for Docker beyond what `pyproject.toml` already declares.

---

## File Structure

- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `docker-compose.yml`
- Modify: `.gitignore` — add Playwright generated-artifact paths.
- Modify: `.github/workflows/ci.yml` — add an `e2e` job.
- Modify: `backend/app/router/graph.py`, `backend/app/handlers/graph_builder.py`, `tests/test_graph_router.py`, `tests/test_session_isolation.py`, `tests/test_graph_builder.py`, `tests/test_graph_state.py` — rename `compose_graph_chat_egine` → `compose_graph_chat_engine`.
- Modify: `backend/app/handlers/index_crud.py`, `backend/app/router/index.py`, `tests/test_index_crud.py`, `tests/test_index_router.py` — remove dead `convert_index_to_file`, rename `citf` → `export_index_to_file`.

---

### Task 1: Dockerfile, .dockerignore, docker-compose.yml

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: `backend/.env` (the exact path `configs.load_env.reload_env_variables()` already reads — `backend/app/configs/load_env.py:25`), `HOST`/`PORT` env vars already honored by `backend/app/main.py:174-177`.

- [ ] **Step 1: Create `.dockerignore`**

```
.venv/
.git/
.github/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
data/
log/
feedback/
.uploads/
fastapi.log
backend.log
tests/playwright/node_modules/
tests/playwright/test-results/
tests/playwright/screenshots/
信息搜集汇总/
docs/
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./backend/
COPY frontend/ ./frontend/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

CMD ["python", "backend/app/main.py"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  cuitcca:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./backend/.env:/app/backend/.env:ro
      - ./data:/app/data
      - ./log:/app/log
      - ./feedback:/app/feedback
      - hf-cache:/root/.cache/huggingface
    restart: unless-stopped

volumes:
  hf-cache:
```

- [ ] **Step 4: Build and smoke-test the image**

```bash
cp backend/.env.example backend/.env   # if not already present; fill in OPENAI_API_KEY before real use
docker compose build
docker compose up -d
curl -sf http://localhost:8000/ 
docker compose logs --tail=50 cuitcca
docker compose down
```

Expected: `curl` returns `{"Hello":"CUITCCA"}`; logs show no import errors (confirms `backend/app` resolved its sibling packages correctly inside the container, matching the `backend.bash` launch pattern).

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml
git commit -m "feat: add Docker deployment (Dockerfile, docker-compose, .dockerignore)"
```

---

### Task 2: Track the Playwright suite and run it in CI

**Files:**
- Modify: `.gitignore`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `tests/playwright/package.json` (existing, declares `@playwright/test` devDependency), `tests/playwright/playwright.config.ts` (existing, `baseURL: 'http://localhost:8000'`).

- [ ] **Step 1: Add generated-artifact paths to `.gitignore`**

Append to `.gitignore`:

```
tests/playwright/node_modules/
tests/playwright/test-results/
tests/playwright/test-results.json
tests/playwright/screenshots/
```

- [ ] **Step 2: Stage the Playwright suite's source files**

```bash
git add -f .gitignore
git add tests/playwright/package.json tests/playwright/package-lock.json \
        tests/playwright/playwright.config.ts tests/playwright/check-pages.ts \
        tests/playwright/*.spec.ts
git status
```

Confirm the `git status` output shows only source files staged — `node_modules/`, `test-results/`, `screenshots/`, and `test-results.json` must NOT appear (the `.gitignore` update from Step 1 should exclude them automatically).

- [ ] **Step 3: Add an `e2e` job to `.github/workflows/ci.yml`**

Append a new job after the existing `security` job in `.github/workflows/ci.yml`:

```yaml
  e2e:
    runs-on: ubuntu-latest
    # Some existing specs exercise the live chat flow, which needs a configured LLM
    # backend that CI doesn't have — treat this job as a signal, not a hard gate,
    # until the suite is split into "static UI" vs "needs a real LLM" specs.
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true

      - name: Install backend dependencies
        run: uv sync --frozen

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install Playwright
        working-directory: tests/playwright
        run: |
          npm ci
          npx playwright install --with-deps chromium

      - name: Prepare env file
        run: cp backend/.env.example backend/.env

      - name: Start backend
        run: |
          nohup uv run python backend/app/main.py > server.log 2>&1 &
          for i in $(seq 1 30); do
            curl -sf http://localhost:8000/ && break
            sleep 2
          done

      - name: Run Playwright suite
        working-directory: tests/playwright
        run: npx playwright test --reporter=list

      - name: Upload server log on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: backend-server-log
          path: server.log

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: tests/playwright/test-results/
          if-no-files-found: ignore
```

- [ ] **Step 4: Verify the workflow file is valid YAML**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`.

- [ ] **Step 5: Commit**

```bash
git add .gitignore .github/workflows/ci.yml
git commit -m "ci: track playwright e2e suite and run it as a non-blocking CI job"
```

---

### Task 3: Rename `compose_graph_chat_egine` typo and de-duplicate index-export helpers

**Files:**
- Modify: `backend/app/router/graph.py`, `backend/app/handlers/graph_builder.py`
- Modify: `tests/test_graph_router.py`, `tests/test_session_isolation.py`, `tests/test_graph_builder.py`, `tests/test_graph_state.py`
- Modify: `backend/app/handlers/index_crud.py:181-215`, `backend/app/router/index.py:15,281`
- Modify: `tests/test_index_crud.py:243-322`, `tests/test_index_router.py:500`

**Interfaces:**
- Produces: `compose_graph_chat_engine()` (corrected spelling) replaces `compose_graph_chat_egine()` everywhere. `export_index_to_file(index, name)` replaces `citf(index, name)` with an identical signature and behavior.

- [ ] **Step 1: Rename `compose_graph_chat_egine` repo-wide**

```bash
grep -rl "compose_graph_chat_egine" backend/ tests/ --include="*.py" | \
  xargs sed -i 's/compose_graph_chat_egine/compose_graph_chat_engine/g'
```

- [ ] **Step 2: Verify the rename is complete and consistent**

```bash
grep -rn "compose_graph_chat_egine" backend/ tests/ --include="*.py"
```

Expected: no output (zero remaining occurrences of the old spelling).

- [ ] **Step 3: Remove the dead `convert_index_to_file` function and its tests**

In `backend/app/handlers/index_crud.py`, delete the `convert_index_to_file` function (the block from `async def convert_index_to_file(index_name: str, file_name: str):` through the line before `async def citf(...)`, i.e. lines 181-200 in the pre-rename file).

In `tests/test_index_crud.py`, delete the entire `ConvertIndexToFileTest` class (both `test_convert_index_to_file_writes_content` and `test_convert_index_to_file_skips_when_index_not_found`, and the class's `setUp`).

- [ ] **Step 4: Rename `citf` to `export_index_to_file`**

In `backend/app/handlers/index_crud.py`, rename the function definition `async def citf(index: VectorStoreIndex, name: str):` to `async def export_index_to_file(index: VectorStoreIndex, name: str):` (keep the body unchanged).

In `backend/app/router/index.py`, update the import (line 15, inside the `from handlers.index_crud import (...)` block) from `citf,` to `export_index_to_file,`, and update the call site (line 281) from `await citf(index, f"{index.index_id}.txt")` to `await export_index_to_file(index, f"{index.index_id}.txt")`.

In `tests/test_index_crud.py`, rename the `CitfTest` class to `ExportIndexToFileTest`, and inside it rename `test_citf_writes_content` → `test_export_index_to_file_writes_content` and `test_citf_creates_directory_when_missing` → `test_export_index_to_file_creates_directory_when_missing`; update both bodies' `await index_crud.citf(...)` calls to `await index_crud.export_index_to_file(...)`.

In `tests/test_index_router.py:500`, update `@patch('router.index.citf')` to `@patch('router.index.export_index_to_file')`, and update whatever variable name that test uses for the mock/assertion to match if it references `citf` by name elsewhere in the same test body (read the test method in full before editing so every reference inside it is updated consistently).

- [ ] **Step 5: Run the full suite and static checks**

```bash
uv run pytest tests/ -v --cov=backend/app
uv run ruff check backend/ tests/
uv run mypy backend/app/ tests/ --ignore-missing-imports
```

Expected: all green, coverage roughly unchanged (net lines removed ≈ net lines renamed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/router/graph.py backend/app/handlers/graph_builder.py \
        backend/app/handlers/index_crud.py backend/app/router/index.py \
        tests/test_graph_router.py tests/test_session_isolation.py \
        tests/test_graph_builder.py tests/test_graph_state.py \
        tests/test_index_crud.py tests/test_index_router.py
git commit -m "refactor: fix compose_graph_chat_engine typo, de-duplicate index export helpers"
```

---

## Self-Review

**Spec coverage:**
- Docker deployment → Task 1. ✓
- Playwright tests tracked + CI e2e job → Task 2. ✓
- API/naming consistency cleanup (scoped) → Task 3, with the response-shape normalization explicitly called out as a non-goal and why. ✓

**Placeholder scan:** No TBD/TODO. Task 2's CI job is intentionally `continue-on-error: true` with an explicit, stated reason (some specs need a real LLM backend CI doesn't have) rather than silently hiding a flaky gate.

**Type/name consistency:** `export_index_to_file` is used identically in its definition (`index_crud.py`), its one call site (`router/index.py`), and both test files. `compose_graph_chat_engine` is verified with a zero-hit grep in Step 2 before committing, so no stale references survive across the three files this session already touched in the other two plans.
