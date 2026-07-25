# Development Guide

本地开发、测试与构建的完整指引。CI 流水线对应内容见 [`.github/workflows/`](../.github/workflows/)。

## Local Setup

```bash
git clone https://github.com/ChuanYuei/CUITCCA.git
cd CUITCCA
uv sync
cp backend/.env.example backend/.env
# edit backend/.env and set OPENAI_API_KEY
```

> 后端依赖用 [uv](https://docs.astral.sh/uv/) 管理（`uv sync` 即装好 Python 依赖）；
> 前端依赖用 npm，见下方 [Run Frontend](#run-frontend)。

## Run Backend

```bash
make dev
# or
cd backend && uv run python app/main.py
```

Server runs at `http://localhost:8522`.

- `CUITCCA_API_KEY` 留空 → 所有读写接口自动跳过鉴权（便于本地联调）。
- 配置后 → 强制 Bearer 鉴权。

## Run Frontend (dev mode with hot reload)

```bash
make frontend-install
make frontend-dev
```

Vite runs at `http://localhost:5173` and proxies `/graph`、`/index`、`/response`、`/manage`
to the backend (`http://localhost:8522`)，见 `frontend/vite.config.ts`。

## Build Frontend (production)

```bash
make frontend-build
```

Assets are written to `backend/app/static/`，由 FastAPI 直接托管（`/web/`）。

## Backend Tests

```bash
make test          # pytest（pyproject.toml 的 addopts 已带 --cov=backend/app）
make lint          # ruff check backend/ tests/
make typecheck     # mypy backend/app/ tests/
make security      # pip-audit + bandit
```

- 覆盖率门槛 90%（`[tool.coverage.report] fail_under = 90`）。
- 标记 `@pytest.mark.eval` 的测试会真实检索/生成，默认不在常规套件里跑（见 [Evals](#evals)）。

## Frontend Tests

前端单元测试用 [Vitest](https://vitest.dev/) + `happy-dom`，覆盖 `src/utils/` 纯逻辑。

```bash
cd frontend
npm test              # vitest run（单次）
npm run test:watch    # 监听模式
npm run test:coverage # 含 v8 覆盖率
```

测试文件位于 `frontend/tests/`（`api.test.ts`、`dom.test.ts`、`toast.test.ts`）。
页面脚本（chat/manage/sidebar/feed_back）因即时 DOM 副作用 + 依赖 marked/DOMPurify 全局变量，
难以单测，不纳入覆盖率统计（见 `frontend/vitest.config.ts` 注释）。
## End-to-End Tests (Playwright)

端到端测试位于 `tests/playwright/`，用 Playwright + Chromium 跑真实浏览器流程。

### 安装

```bash
cd tests/playwright
npm ci
npx playwright install --with-deps chromium
```

### 运行

需要后端先跑起来（`make dev`），然后：

```bash
cd tests/playwright
npx playwright test                          # 跑全部 spec
npx playwright test --grep-invert "真实收发"  # 跳过需要 LLM 的真实问答 spec
```

- `playwright.config.ts` 默认 `baseURL: http://localhost:8522`、`viewport: 1280x720`、headless。
- 真实问答 spec（`test-chat-e2e.spec.ts`）需要后端能调用 LLM（`OPENAI_API_KEY`）；未配置时
  CI 会自动跳过，仅运行 UI 结构/交互类用例（见 `.github/workflows/e2e.yml`）。

### CI

`.github/workflows/e2e.yml` 在 PR 改动前端 / 后端路由 / Playwright 用例 / 工作流时触发：
构建前端 → 启动后端 → 安装 Chromium → 跑 Playwright → 上传报告与后端日志 artifact。

## Screenshots

README 引用的 Demo 截图（`docs/screenshots/*.png`）由 `scripts/take_screenshots.py` 生成。

```bash
# 前置：后端已运行（make dev），且已装 Playwright + Chromium
pip install playwright && playwright install chromium

uv run python scripts/take_screenshots.py
# 自定义地址/输出目录：
uv run python scripts/take_screenshots.py --base-url http://localhost:8522 --output-dir docs/screenshots
```

脚本会逐页截图，单页失败不中断其余：

- `chat.png` — 模拟输入一条问题、点发送、等回复到达后再截（LLM 未配置则退化为仅含用户消息）。
- `manage.png` — 等 `#index-select` 加载出真实索引选项后再截。
- `feed_back.png` / `use_function.png` — 加载完成后直接截。

> 截图不入库，需维护者本地跑一次后提交。README 在截图缺失时显示 broken image 是正常的。

## CI

GitHub Actions 流水线（`.github/workflows/`）：

| Workflow | 触发 | 内容 |
|----------|------|------|
| `ci.yml` | push / PR | ruff、mypy、pytest+coverage（Python 3.12 / 3.13 矩阵）、tsc、前端 build、pip-audit |
| `e2e.yml` | PR 改动前端/路由/Playwright | Playwright E2E（见上） |
| `release.yml` | tag | 发布产物 |

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