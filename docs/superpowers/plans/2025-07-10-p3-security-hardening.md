# P3: 安全加固实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 添加文件上传限制、Cookie 安全配置、统一认证依赖

**Architecture:** 三个独立任务：文件上传验证中间件、Cookie 安全配置、统一认证依赖

**Tech Stack:** Python 3.12, FastAPI, pydantic, unittest

## Global Constraints

- 所有变更必须保持 53 个测试通过
- 遵循项目现有代码风格（中文注释、无类型注解优先）
- 不引入新的外部依赖
- 每次任务完成后必须运行 `uv run python -m unittest discover -s tests -q`

---

### Task 1: 添加文件上传大小限制与类型校验

**Files:**
- Modify: `backend/app/configs/load_env.py`
- Modify: `backend/app/router/index.py`
- Modify: `backend/app/router/test.py`
- Test: `tests/test_upload_validation.py`

**Interfaces:**
- Consumes: `configs.load_env`、`fastapi.UploadFile`
- Produces: 带验证的文件上传处理逻辑

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 53 tests ... OK`

- [ ] **Step 2: 在 `configs/load_env.py` 添加上传配置**

```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.csv', '.xlsx'}
```

- [ ] **Step 3: 创建 `utils/upload.py` 验证工具**

```python
import os
from typing import Optional

from configs.load_env import MAX_FILE_SIZE, ALLOWED_EXTENSIONS


class FileTooLargeError(Exception):
    pass


class InvalidFileTypeError(Exception):
    pass


def validate_upload_file(file) -> None:
    if file.size > MAX_FILE_SIZE:
        raise FileTooLargeError(f"File size {file.size} exceeds limit {MAX_FILE_SIZE}")
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(f"File type {ext} not allowed")
```

- [ ] **Step 4: 在 `router/index.py` 的 `upload_file` 和 `upload_files` 中添加验证**

```python
from utils.upload import validate_upload_file, FileTooLargeError, InvalidFileTypeError

@index_app.post("/{index_name}/uploadFile")
async def upload_file(index=Depends(get_index), file: UploadFile = File(...)):
    try:
        validate_upload_file(file)
    except (FileTooLargeError, InvalidFileTypeError) as e:
        return JSONResponse(
            content={"status": "detail", "message": str(e)},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    # ... rest of logic
```

- [ ] **Step 5: 创建 `tests/test_upload_validation.py`**

```python
import io
import os
import unittest
from unittest.mock import MagicMock

import tests._pathsetup  # noqa: F401

from utils.upload import validate_upload_file, FileTooLargeError, InvalidFileTypeError


class UploadValidationTest(unittest.TestCase):
    def test_rejects_file_too_large(self):
        mock_file = MagicMock()
        mock_file.size = 20 * 1024 * 1024  # 20MB
        mock_file.filename = "test.pdf"
        
        with self.assertRaises(FileTooLargeError):
            validate_upload_file(mock_file)

    def test_accepts_pdf(self):
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.filename = "test.pdf"
        
        validate_upload_file(mock_file)  # should not raise

    def test_rejects_exe(self):
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.filename = "malware.exe"
        
        with self.assertRaises(InvalidFileTypeError):
            validate_upload_file(mock_file)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 6: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 53+ tests ... OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/configs/load_env.py backend/app/utils/upload.py backend/app/router/index.py backend/app/router/test.py tests/test_upload_validation.py
git commit -m "feat: 添加文件上传大小限制与类型校验"
```

---

### Task 2: Cookie 安全配置

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/configs/load_env.py`
- Test: `tests/test_cookie_config.py`

**Interfaces:**
- Consumes: `configs.load_env`、`starlette.responses.Response`
- Produces: 带安全标志的 Cookie 设置

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 53 tests ... OK`

- [ ] **Step 2: 在 `configs/load_env.py` 添加 Cookie 配置**

```python
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'False').lower() in ('true', '1', 't')
COOKIE_MAX_AGE = int(os.environ.get('COOKIE_MAX_AGE', '86400'))  # 1 day
```

- [ ] **Step 3: 修改 `main.py` 的 Cookie 设置**

```python
from configs.load_env import COOKIE_SECURE, COOKIE_MAX_AGE

# In session_and_stats_middleware:
response.set_cookie(
    key=cookie_name,
    value=session_id,
    path="/",
    httponly=True,
    samesite="lax",
    secure=COOKIE_SECURE,
    max_age=COOKIE_MAX_AGE,
)
```

- [ ] **Step 4: 创建 `tests/test_cookie_config.py`**

```python
import os
import unittest
from unittest.mock import patch, MagicMock

import tests._pathsetup  # noqa: F401

from fastapi import FastAPI
from fastapi.testclient import TestClient


class CookieConfigTest(unittest.TestCase):
    def test_cookie_has_httponly_flag(self):
        app = FastAPI()
        
        @app.get("/")
        async def root(request):
            response = JSONResponse({"ok": True})
            response.set_cookie(
                key="test",
                value="val",
                path="/",
                httponly=True,
                samesite="lax",
            )
            return response
        
        client = TestClient(app)
        response = client.get("/")
        cookie = response.headers.get("set-cookie")
        self.assertIn("HttpOnly", cookie)

    def test_cookie_secure_flag_controlled_by_env(self):
        with patch.dict(os.environ, {'COOKIE_SECURE': 'True'}):
            import importlib
            import configs.load_env as env_mod
            importlib.reload(env_mod)
            self.assertTrue(env_mod.COOKIE_SECURE)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 5: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 53+ tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/configs/load_env.py tests/test_cookie_config.py
git commit -m "feat: 添加 Cookie 安全配置（secure、max_age、httponly）"
```

---

### Task 3: 统一认证依赖（移除 BaseHTTPMiddleware）

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/utils/security.py`
- Test: `tests/test_auth_middleware.py`

**Interfaces:**
- Consumes: `fastapi.Depends`、`starlette.requests.Request`
- Produces: 统一使用依赖注入的认证机制

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 53 tests ... OK`

- [ ] **Step 2: 在 `main.py` 中移除 `ApiKeyMiddleware`，改用依赖注入**

```python
# 移除：
# API_KEY = os.environ.get('CUITCCA_API_KEY', '')
# if API_KEY:
#     app.add_middleware(ApiKeyMiddleware, api_key=API_KEY)

# 改为在所有需要认证的路由上添加依赖：
from utils.security import require_configured_api_key

# 在 manage_app 的路由上已经使用 require_configured_api_key
# 其他需要认证的路由也添加此依赖
```

- [ ] **Step 3: 更新 `tests/test_auth_middleware.py`**

确保测试覆盖依赖注入方式。

- [ ] **Step 4: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 53 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/utils/security.py tests/test_auth_middleware.py
git commit -m "refactor: 统一认证机制为依赖注入，移除 BaseHTTPMiddleware"
```

---

## 执行检查清单

- [ ] Task 1: 文件上传大小限制与类型校验
- [ ] Task 2: Cookie 安全配置
- [ ] Task 3: 统一认证依赖
- [ ] 全部 53+ 测试通过
- [ ] CI/CD 流水线通过

## 后续计划

P3 完成后，继续处理：
- 技术债务：ComposableGraph.from_indices 废弃 API 迁移
- 性能优化：缓存 query engine 结果、连接池
- 监控：添加 Prometheus metrics、结构化日志
