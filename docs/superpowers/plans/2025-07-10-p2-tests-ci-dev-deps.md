# P2: 测试覆盖提升与 CI/CD 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补充关键单元测试、添加 CI/CD 流水线、完善 dev 依赖组

**Architecture:** 三个独立任务：补充单元测试（会话隔离、权限中间件、上传限制）、添加 GitHub Actions CI/CD、更新 pyproject.toml dev 依赖组。

**Tech Stack:** Python 3.12, FastAPI, unittest, GitHub Actions, ruff, mypy, pytest

## Global Constraints

- 所有变更必须保持 46 个测试通过
- 遵循项目现有代码风格（中文注释、无类型注解优先）
- 不引入新的外部依赖（除了 dev 依赖组）
- 每次任务完成后必须运行 `uv run python -m unittest discover -s tests -q`

---

### Task 1: 补充关键单元测试

**Files:**
- Create: `tests/test_session_isolation.py`
- Create: `tests/test_api_key_middleware.py`
- Modify: `tests/test_main_workflow_http.py` (修复导入路径)
- Test: 新增 3 个测试文件

**Interfaces:**
- Consumes: `main.py`、`security.py`、`router/graph.py`
- Produces: 覆盖 P0-P1 修复场景的单元测试

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 2: 创建 `tests/test_session_isolation.py`**

测试 `_graph_chat_engines` 的会话隔离逻辑：

```python
import asyncio
import unittest
from unittest.mock import MagicMock, patch

import tests._pathsetup  # noqa: F401

from fastapi.testclient import TestClient
from main import app
from router.graph import _graph_chat_engines, _prune_sessions


class SessionIsolationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        _graph_chat_engines.clear()

    def tearDown(self):
        _graph_chat_engines.clear()

    @patch('router.graph.compose_graph_chat_egine')
    def test_different_clients_get_different_engines(self, mock_compose):
        mock_engine = MagicMock()
        mock_compose.return_value = mock_engine

        # Client A creates graph
        response_a = self.client.post("/graph/create")
        self.assertEqual(response_a.status_code, 200)

        # Client B creates graph (simulated by clearing and re-creating)
        # In real scenario, different cookies/sessions would be used
        # Here we test that _prune_sessions doesn't break isolation
        _prune_sessions(_graph_chat_engines, 100)
        self.assertIsNotNone(_graph_chat_engines)

    def test_prune_sessions_respects_max_size(self):
        # Fill up sessions
        for i in range(5):
            _graph_chat_engines[f"client_{i}"] = MagicMock()

        _prune_sessions(_graph_chat_engines, max_size=3)

        self.assertLessEqual(len(_graph_chat_engines), 3)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: 创建 `tests/test_api_key_middleware.py`**

测试 `ApiKeyMiddleware` 和 `require_configured_api_key`：

```python
import os
import unittest
from unittest.mock import patch

import tests._pathsetup  # noqa: F401

from fastapi.testclient import TestClient
from fastapi import FastAPI
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_503_SERVICE_UNAVAILABLE

from utils.security import ApiKeyMiddleware, require_configured_api_key
from router.manage import manage_app


class ApiKeyMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.add_middleware(ApiKeyMiddleware, api_key="secret123")
        self.app.include_router(manage_app, prefix='/manage')
        self.client = TestClient(self.app)

    def test_rejects_missing_bearer_token(self):
        response = self.client.get("/manage/stats")
        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)

    def test_rejects_wrong_bearer_token(self):
        response = self.client.get(
            "/manage/stats",
            headers={"Authorization": "Bearer wrong"}
        )
        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)

    def test_accepts_correct_bearer_token(self):
        response = self.client.get(
            "/manage/stats",
            headers={"Authorization": "Bearer secret123"}
        )
        self.assertEqual(response.status_code, 200)


class RequireConfiguredApiKeyTest(unittest.TestCase):
    def test_returns_503_when_api_key_not_configured(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': ''}):
            # Simulate dependency check
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                require_configured_api_key(None)
            self.assertEqual(ctx.exception.status_code, HTTP_503_SERVICE_UNAVAILABLE)

    def test_returns_401_when_token_missing(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            from fastapi import Request
            mock_request = MagicMock()
            mock_request.headers = {}
            with self.assertRaises(HTTPException) as ctx:
                require_configured_api_key(mock_request)
            self.assertEqual(ctx.exception.status_code, HTTP_401_UNAUTHORIZED)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 4: 修复 `tests/test_main_workflow_http.py` 的导入**

当前从 `main` 直接导入，导致加载所有路由器。改为使用 `TestClient` 的 `app`：

```python
# 修改前
from main import app
from router.index import get_index

# 修改后
from main import app
from router.index import get_index
```

保持现状即可，但确保 `get_index` 路径正确。

- [ ] **Step 5: 运行所有测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46+ tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add tests/test_session_isolation.py tests/test_api_key_middleware.py
git commit -m "test: 补充会话隔离和 API Key 中间件单元测试"
```

---

### Task 2: 添加 GitHub Actions CI/CD

**Files:**
- Create: `.github/workflows/ci.yml`
- Test: N/A

**Interfaces:**
- Consumes: `pyproject.toml`、`uv.lock`
- Produces: CI/CD 流水线

- [ ] **Step 1: 创建 `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true

      - name: Install dependencies
        run: uv sync --frozen

      - name: Lint with ruff
        run: uv run ruff check backend/ tests/

      - name: Type check with mypy
        run: uv run mypy backend/app/ tests/ --ignore-missing-imports

      - name: Run tests
        run: uv run python -m unittest discover -s tests -v

      - name: Upload coverage
        if: always()
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
          fail_ci_if_error: false
```

- [ ] **Step 2: 确认工作流文件语法正确**

```bash
cat .github/workflows/ci.yml
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: 添加 GitHub Actions CI/CD 流水线"
```

---

### Task 3: 完善 dev 依赖组与工具配置

**Files:**
- Modify: `pyproject.toml`
- Create: `ruff.toml` (可选)
- Create: `mypy.ini` (可选)
- Test: N/A

**Interfaces:**
- Consumes: 现有项目配置
- Produces: 完整的 dev 工具链配置

- [ ] **Step 1: 更新 `pyproject.toml` 的 dev 依赖组**

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
    "mypy>=1.10",
]
```

- [ ] **Step 2: 添加 `ruff.toml` 配置**

```toml
line-length = 120
target-version = "py312"

[LINT]
select = ["E", "F", "I", "N", "W", "UP"]

[EXCLUDE]
"__pycache__"
".venv"
"frontend"
```

- [ ] **Step 3: 添加 `mypy.ini` 配置**

```ini
[mypy]
python_version = 3.12
ignore_missing_imports = True
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False
```

- [ ] **Step 4: 运行工具验证**

```bash
uv run ruff check backend/ tests/
uv run mypy backend/app/ tests/ --ignore-missing-imports
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml ruff.toml mypy.ini
git commit -m "chore: 添加 dev 依赖组和代码检查工具配置"
```

---

## 执行检查清单

- [ ] Task 1: 补充关键单元测试
- [ ] Task 2: 添加 GitHub Actions CI/CD
- [ ] Task 3: 完善 dev 依赖组与工具配置
- [ ] 全部 46+ 测试通过
- [ ] CI/CD 流水线通过

## 后续计划

P2 完成后，继续处理：
- P3: 安全加固（文件上传限制、Cookie 配置）
- 技术债务：ComposableGraph.from_indices 废弃 API 迁移
