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

### 一键启动（推荐）

```bash
./backend.bash     # Linux / macOS
# backend.bat      # Windows
```

脚本依次完成：清理 8522 端口占用 → `.venv` 不存在时 `uv sync` 装依赖 →
`backend/.env` 不存在时从 `.env.example` 复制 → `nohup` 守护启动（崩溃自动
重启），日志写项目根目录 `fastapi.log`。**停止 / 重启 = 再跑一次脚本**
（会自动清掉旧进程）。

验证：

```bash
curl http://localhost:8522/   # 期望 {"Hello":"CUITCCA"}
tail -f fastapi.log           # "Application startup complete" 即就绪
```

### 前台运行（调试用）

```bash
uv run python backend/app/main.py   # Ctrl+C 停止
# 开发模式（热重载）：
make dev
```

> **`make dev` 的坑**：它内部执行 `cd backend && python -m uvicorn ...`，依赖
> 当前 shell 能把 `python` 解析到 venv（先 `source .venv/bin/activate` 或把
> `.venv/bin` 加进 `PATH`）。本机若没装系统 Python 或 venv 缺 `activate`，裸
> shell 直接 `make dev` 会报 `command not found` / `ModuleNotFoundError`，此时
> 一律改用 `./backend.bash` 或 `uv run`。

Server runs at `http://localhost:8522`（`/web/` 前端，`/docs` API 文档）。

- `CUITCCA_API_KEY` 留空 → 所有读写接口自动跳过鉴权（便于本地联调）。
- 配置后 → 强制 Bearer 鉴权。

### 启动排障

| 现象 | 原因 / 处理 |
|------|-------------|
| 启动即报 `ModuleNotFoundError` | `.venv` 是空壳（目录在但依赖没装）：脚本只在目录不存在时才 `uv sync`，手动补一次 `uv sync`（可选 `--extra ocr`） |
| 端口 8522 被占用 | 脚本会自动杀掉占用进程；手动 `lsof -i :8522` 查、`kill <pid>` 清 |
| 首次启动很慢 / CPU 满载 | 正常：正在下载嵌入与重排模型（bge-reranker-v2-m3 约 2.2GB），缓存后每次约 10~30 秒 |
| `fastapi.log` 一直是空的 | 启动早期输出被缓冲 / 模型加载未完成；出现 `Application startup complete` 后再看 |
| 后台进程随终端/宿主环境退出 | `nohup` 能扛 SIGHUP，但若宿主环境按进程组回收子进程（如 CI / agent 沙箱、SSH 会话异常断开），守护循环仍可能被带走；此时重新跑一次 `./backend.bash` 拉起即可 |
| `.venv/bin/activate` 不存在 | 个别 uv 版本创建的 venv 无 activate 脚本，脚本里 `source` 那步报错但**不影响启动**（守护进程直接用 `.venv/bin/python`） |

> 也见根目录 `README.md` 的 [一键启动脚本做了什么事](../README.md#一键启动脚本做了什么事) 一节。

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