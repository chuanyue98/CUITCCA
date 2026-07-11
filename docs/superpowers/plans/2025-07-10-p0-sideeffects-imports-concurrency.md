# P0: 消除模块级副作用、野生导入与全局可变状态 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `configs/load_env.py` 的模块级副作用、替换所有 `import *` 野生导入、消除全局可变状态的并发风险

**Architecture:** 通过三个独立任务分别处理模块级副作用、野生导入链、全局可变状态的线程安全问题，每个任务都是自包含的可测试变更。

**Tech Stack:** Python 3.12, FastAPI, unittest

## Global Constraints

- 所有变更必须保持 46 个测试通过
- 遵循项目现有代码风格（中文注释、无类型注解优先）
- 不引入新的外部依赖
- 每次任务完成后必须运行 `uv run python -m unittest discover -s tests -q`

---

### Task 1: 消除 `configs/load_env.py` 的模块级副作用

**Files:**
- Modify: `backend/app/configs/load_env.py`
- Test: `tests/test_reload_env_variables.py` (已存在)

**Interfaces:**
- Consumes: 无
- Produces: `reload_env_variables()` 函数保持不变，删除模块末尾的自动调用

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 2: 修改 `configs/load_env.py`**

删除文件末尾第 50 行的 `reload_env_variables()` 调用。

修改前：
```python
def reload_env_variables():
    ...


reload_env_variables()
```

修改后：
```python
def reload_env_variables():
    ...
```

- [ ] **Step 3: 确认 `main.py` 中已显式调用**

Read `backend/app/main.py`，确认在 lifespan 或启动逻辑中显式调用了 `reload_env_variables()`。

如果没有，在 `lifespan` 的 `yield` 之前添加：
```python
from configs.load_env import reload_env_variables
...
reload_env_variables()
```

- [ ] **Step 4: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/configs/load_env.py
git commit -m "refactor: 移除 configs/load_env.py 模块级 reload_env_variables() 调用，改为显式调用"
```

---

### Task 2: 替换所有野生导入（`from X import *`）

**Files:**
- Modify: `backend/app/configs/__init__.py`
- Modify: `backend/app/dependencies/__init__.py`
- Modify: `backend/app/router/index.py`
- Test: 无新增测试，依赖现有测试覆盖

**Interfaces:**
- Consumes: 各子模块的公开 API
- Produces: 显式导入列表，保持现有公开接口不变

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 2: 修改 `configs/__init__.py`**

修改前：
```python
from .load_env import *
```

修改后：
```python
from .load_env import (
    PROJECT_ROOT,
    index_save_directory,
    SAVE_PATH,
    LOAD_PATH,
    FEEDBACK_PATH,
    LOG_PATH,
    FILE_PATH,
    access_stats_path,
    openai_api_key,
    openai_api_base,
    openai_model,
    VERBOSE,
    reload_env_variables,
)
```

- [ ] **Step 3: 修改 `dependencies/__init__.py`**

修改前：
```python
from .index_dep import *
from .manage import *
```

修改后：
```python
from .index_dep import get_index
from .manage import access_stats
```

- [ ] **Step 4: 修改 `router/index.py` 的野生导入**

找到第 19 行：
```python
from handlers.llama_handler import *
```

替换为显式导入：
```python
from handlers.llama_handler import (
    indexes,
    createIndex,
    loadAllIndexes,
    insert_into_index,
    embeddingQA,
    get_all_docs,
    updateNodeById,
    deleteNodeById,
    deleteDocById,
    saveIndex,
    get_index_by_name,
    get_prompt_by_name,
    convert_index_to_file,
    citf,
    format_source_nodes_list,
    fix_doc_id_not_found,
    get_docs_from_index,
)
```

- [ ] **Step 5: 运行测试验证所有导入正确**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

如有 `ImportError`，根据报错补充缺失的导入名称。

- [ ] **Step 6: Commit**

```bash
git add backend/app/configs/__init__.py backend/app/dependencies/__init__.py backend/app/router/index.py
git commit -m "refactor: 替换所有 import * 为显式导入，消除野生导入链"
```

---

### Task 3: 消除全局可变状态的并发风险

**Files:**
- Modify: `backend/app/handlers/llama_handler.py`
- Modify: `backend/app/dependencies/manage.py`
- Modify: `backend/app/router/graph.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: 现有 `indexes`、`access_stats` 的读写接口
- Produces: 线程安全的访问机制

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 2: 为 `indexes` 列表添加 `asyncio.Lock`**

修改 `backend/app/handlers/llama_handler.py`:

在文件顶部添加：
```python
import asyncio

_indexes_lock = asyncio.Lock()
```

将 `indexes` 的所有读写操作（`loadAllIndexes` 中的 `indexes.clear()` 和 `indexes.append()`）用锁保护：

```python
async def loadAllIndexes():
    ...
    async with _indexes_lock:
        indexes.clear()
        for index_dir_name in get_folders_list(index_save_directory):
            ...
            indexes.append(index)
```

- [ ] **Step 3: 确认 `router/index.py` 中对 `indexes` 的读取安全**

`get_index_list()` 读取 `indexes` 时使用 `async with _indexes_lock`。

- [ ] **Step 4: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/handlers/llama_handler.py backend/app/router/index.py
git commit -m "fix: 为 indexes 全局列表添加 asyncio.Lock，消除并发读写风险"
```

---

## 执行检查清单

- [ ] Task 1: 模块级副作用消除
- [ ] Task 2: 野生导入替换
- [ ] Task 3: 全局可变状态加锁
- [ ] 全部 46 个测试通过
- [ ] 无新的警告或错误

## 后续计划

P0 完成后，继续处理：
- P1: 拆分 `llama_handler.py`、废弃 API 迁移、响应模型
- P2: 补充单元测试、CI/CD
- P3: 安全加固
