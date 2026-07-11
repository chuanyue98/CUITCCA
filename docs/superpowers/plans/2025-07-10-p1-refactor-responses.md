# P1: 代码质量提升 — 拆分 God Object、废弃 API 迁移、响应模型 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 359 行的 `handlers/llama_handler.py` 拆分为职责单一的文件，迁移已废弃的 llama-index API，为所有端点添加响应模型

**Architecture:** 将 `llama_handler.py` 拆分为 4 个模块（index_crud、graph_builder、qa_generator、file_converters），保留 `llama_handler.py` 作为向后兼容的 re-export 层；废弃 API 的迁移在拆分过程中自然完成；响应模型统一放在 `models/response.py`。

**Tech Stack:** Python 3.12, FastAPI, llama-index 0.14.x, unittest

## Global Constraints

- 所有变更必须保持 46 个测试通过
- 遵循项目现有代码风格（中文注释、无类型注解优先）
- 不引入新的外部依赖
- 每次任务完成后必须运行 `uv run python -m unittest discover -s tests -q`
- 拆分后 `handlers/llama_handler.py` 保留作为 re-export 层，避免一次性修改所有 import 语句

---

### Task 1: 拆分 `handlers/llama_handler.py` 为 index_crud 和 file_converters

**Files:**
- Create: `backend/app/handlers/index_crud.py`
- Create: `backend/app/handlers/file_converters.py`
- Modify: `backend/app/handlers/llama_handler.py` → 改为 re-export 层
- Test: `tests/test_llama_handler.py` (更新 import 路径)

**Interfaces:**
- Consumes: `configs.load_env`、`utils.file`、`utils.logger`、`utils.llama.get_nodes_from_file`
- Produces: `index_crud.py` 提供索引 CRUD 函数；`file_converters.py` 提供文件转换函数；`llama_handler.py` 重新导出所有公开 API

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 2: 创建 `handlers/index_crud.py`**

从 `llama_handler.py` 提取以下函数：
- `createIndex(index_name)`
- `loadAllIndexes()`（已改为 async）
- `saveIndex(index)`
- `get_all_docs(index)`
- `updateNodeById(index_, id_, text)`
- `deleteNodeById(index, id_)`
- `deleteDocById(index, id_)`
- `get_index_by_name(index_name)`
- `fix_doc_id_not_found(index, doc_id)`
- `get_docs_from_index(index, doc_id)`
- `convert_index_to_file(index_name, file_name)`
- `citf(index, name)`
- `format_source_nodes_list(node_with_score_list)`

文件结构：
```python
import asyncio
import json
import logging
import os

from llama_index.core import VectorStoreIndex, load_index_from_storage, StorageContext
from llama_index.core.indices.base import BaseIndex

from configs.load_env import index_save_directory
from utils.file import get_folders_list
from utils.logger import customer_logger

_indexes_lock = asyncio.Lock()
indexes = []

# ... 所有 CRUD 函数 ...
```

- [ ] **Step 3: 创建 `handlers/file_converters.py`**

从 `llama_handler.py` 提取：
- `remove_vector_store(path, doc_id)`
- `remove_index_store(path, doc_id)`
- `remove_docstore(path, doc_id)`

- [ ] **Step 4: 修改 `handlers/llama_handler.py` 为 re-export 层**

```python
from handlers.index_crud import (
    indexes,
    _indexes_lock,
    createIndex,
    loadAllIndexes,
    saveIndex,
    get_all_docs,
    updateNodeById,
    deleteNodeById,
    deleteDocById,
    get_index_by_name,
    fix_doc_id_not_found,
    get_docs_from_index,
    convert_index_to_file,
    citf,
    format_source_nodes_list,
)
from handlers.file_converters import (
    remove_vector_store,
    remove_index_store,
    remove_docstore,
)
```

- [ ] **Step 5: 更新 `tests/test_llama_handler.py` 的 import**

```python
import handlers.llama_handler as lh
# 保持不变，因为 llama_handler.py 仍然 re-export 所有 API
```

- [ ] **Step 6: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/handlers/index_crud.py backend/app/handlers/file_converters.py backend/app/handlers/llama_handler.py
git commit -m "refactor: 拆分 llama_handler.py 为 index_crud.py 和 file_converters.py，保留 re-export 层"
```

---

### Task 2: 拆分剩余职责到 graph_builder 和 qa_generator

**Files:**
- Create: `backend/app/handlers/graph_builder.py`
- Create: `backend/app/handlers/qa_generator.py`
- Modify: `backend/app/handlers/llama_handler.py`
- Modify: `backend/app/router/graph.py`
- Modify: `backend/app/router/index.py`
- Test: 无新增测试

**Interfaces:**
- Consumes: `configs.config.Prompts`、`configs.load_env.VERBOSE`、`llama_index.core` 各组件
- Produces: `graph_builder.py` 提供图谱构建函数；`qa_generator.py` 提供 QA 生成函数

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 2: 创建 `handlers/graph_builder.py`**

从 `llama_handler.py` 提取：
- `compose_graph_chat_egine()`
- `compose_graph_query_engine(streaming=False)`
- `summary_index(index)`

```python
import asyncio
import re
import logging

from llama_index.core import ComposableGraph, ListIndex, TreeIndex, get_response_synthesizer
from llama_index.core.chat_engine import CondenseQuestionChatEngine
from llama_index.core.chat_engine.types import BaseChatEngine
from llama_index.core.indices.query.base import BaseQueryEngine

from configs.config import Prompts
from configs.load_env import VERBOSE
from handlers.index_crud import indexes, _indexes_lock


async def compose_graph_chat_egine() -> BaseChatEngine:
    async with _indexes_lock:
        summaries = [i.summary for i in indexes]
        _indexes_snapshot = list(indexes)
    
    graph = ComposableGraph.from_indices(
        ListIndex,
        _indexes_snapshot,
        index_summaries=summaries,
    )
    custom_query_engines = {
        index.index_id: index.as_query_engine(child_branch_factor=2)
        for index in _indexes_snapshot
    }
    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=graph.as_query_engine(
            text_qa_template=Prompts.QA_PROMPT.value,
            refine_template=Prompts.REFINE_PROMPT.value,
            streaming=True,
            similarity_top_k=3,
            verbose=VERBOSE,
            custom_query_engines=custom_query_engines,
        ),
        condense_question_prompt=Prompts.CONDENSE_QUESTION_PROMPT.value,
        verbose=VERBOSE,
        chat_mode="condense_question",
    )
    return chat_engine


async def compose_graph_query_engine(streaming=False) -> BaseQueryEngine:
    async with _indexes_lock:
        summaries = [i.summary for i in indexes]
        _indexes_snapshot = list(indexes)
    
    graph = ComposableGraph.from_indices(
        TreeIndex,
        _indexes_snapshot,
        index_summaries=summaries,
    )
    custom_query_engines = {
        index.index_id: index.as_query_engine(child_branch_factor=3)
        for index in _indexes_snapshot
    }
    response_synthesizer = get_response_synthesizer(structured_answer_filtering=True)

    query_engine = graph.as_query_engine(
        text_qa_template=Prompts.QA_PROMPT.value,
        refine_template=Prompts.REFINE_PROMPT.value,
        streaming=streaming,
        similarity_top_k=3,
        verbose=VERBOSE,
    )
    return query_engine


async def summary_index(index):
    summary = await index.as_query_engine(response_mode="tree_summarize").aquery(
        "总结，生成文章摘要，要覆盖所有要点，方便后续检索,不需要详细内容，只需要关键信息，方便后续检索")
    summary_str = re.sub(r"\s+", " ", str(summary))
    summary_str = re.sub(r"[^\w\s]", "", summary_str)
    logging.info(f"Summary: {summary_str}")
    return summary_str
```

- [ ] **Step 3: 创建 `handlers/qa_generator.py`**

从 `llama_handler.py` 提取：
- `generate_qa_batched(contents, prompt=None)`（已在 `utils/llama.py` 中，确认是否需要移动）
- `build_qa_generation_prompt(custom_prompt)`（已在 `utils/llama.py` 中）
- `get_nodes_from_file(file_path)`（已在 `utils/llama.py` 中）

确认：这三个函数已在 `utils/llama.py` 中，无需重复提取。

- [ ] **Step 4: 更新 `handlers/llama_handler.py` re-export**

```python
from handlers.index_crud import (
    indexes,
    _indexes_lock,
    createIndex,
    loadAllIndexes,
    saveIndex,
    get_all_docs,
    updateNodeById,
    deleteNodeById,
    deleteDocById,
    get_index_by_name,
    fix_doc_id_not_found,
    get_docs_from_index,
    convert_index_to_file,
    citf,
    format_source_nodes_list,
)
from handlers.file_converters import (
    remove_vector_store,
    remove_index_store,
    remove_docstore,
)
from handlers.graph_builder import (
    compose_graph_chat_egine,
    compose_graph_query_engine,
    summary_index,
)
```

- [ ] **Step 5: 更新 `router/graph.py` 的 import**

将 `from handlers.llama_handler import compose_graph_chat_egine, ...` 改为从新模块导入（或保持从 `llama_handler` re-export 导入，无需修改）

- [ ] **Step 6: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 7: Commit**

```bash
git add backend/app/handlers/graph_builder.py backend/app/handlers/llama_handler.py
git commit -m "refactor: 提取 graph_builder.py，将图谱构建逻辑从 llama_handler 中分离"
```

---

### Task 3: 废弃 API 迁移 — 替换 ListIndex/TreeIndex/ServiceContext/Prompt

**Files:**
- Modify: `backend/app/handlers/graph_builder.py`
- Modify: `backend/app/configs/config.py`
- Test: 无

**Interfaces:**
- Consumes: `llama_index.core` 新版 API
- Produces: 使用非废弃 API 的实现

- [ ] **Step 1: 确认当前测试通过**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 2: 迁移 `Prompt` → `PromptTemplate`**

修改 `backend/app/configs/config.py`：

```python
from llama_index.core import PromptTemplate

class Prompts(Enum):
    QA_PROMPT = PromptTemplate(
        "你是成都信息工程大学校园小助手，仅回答学校有关的问题，其他问题都不回答\n"
        ...
    )
    ...
```

- [ ] **Step 3: 移除 `ServiceContext` 引用**

检查 `handlers/graph_builder.py` 中是否使用了 `ServiceContext`，如已移除则跳过。

- [ ] **Step 4: 评估 ListIndex/TreeIndex 迁移**

`ComposableGraph.from_indices` 在新版 llama-index 中已标记为废弃。调研替代方案：
- 使用 `llama_index.core.base_query_engine.BaseQueryEngine` 组合
- 或保留当前实现（因为 `ComposableGraph` 在 0.14.x 中仍可用，只是标记废弃）

如果迁移成本过高，记录为技术债务，在 TODO 中标记。

- [ ] **Step 5: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/configs/config.py backend/app/handlers/graph_builder.py
git commit -m "refactor: 迁移 Prompt 为 PromptTemplate，移除 ServiceContext 引用"
```

---

### Task 4: 添加响应模型

**Files:**
- Create: `backend/app/models/response.py`
- Modify: `backend/app/router/index.py`
- Modify: `backend/app/router/graph.py`
- Modify: `backend/app/router/response.py`
- Modify: `backend/app/router/manage.py`
- Modify: `backend/app/router/test.py`
- Test: 无

**Interfaces:**
- Consumes: `pydantic.BaseModel`
- Produces: 所有端点的响应模型

- [ ] **Step 1: 创建 `models/response.py`**

```python
from pydantic import BaseModel
from typing import List, Optional, Any


class IndexListResponse(BaseModel):
    indexes: List[str]


class QueryResponse(BaseModel):
    response: str


class SourceNode(BaseModel):
    id: str
    text: str
    score: Optional[float] = None


class QuerySourcesResponse(BaseModel):
    source_nodes: List[SourceNode]


class UploadResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    status: str = "detail"
    message: str


class StatsResponse(BaseModel):
    total_visits: int
    ip_count: int
    user_visits: dict
    endpoint_visits: dict


class FeedbackResponse(BaseModel):
    message: str


class EnvUpdateResponse(BaseModel):
    message: str
```

- [ ] **Step 2: 逐步迁移各路由使用响应模型**

按优先级迁移：
1. `router/response.py` — 最简单的 QueryResponse
2. `router/manage.py` — StatsResponse、FeedbackResponse、EnvUpdateResponse
3. `router/index.py` — 各种响应
4. `router/graph.py` — QueryResponse、QuerySourcesResponse

- [ ] **Step 3: 运行测试验证**

Run: `uv run python -m unittest discover -s tests -q`
Expected: `Ran 46 tests ... OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/response.py backend/app/router/*.py
git commit -m "feat: 添加响应模型，为所有端点返回类型提供类型安全"
```

---

## 执行检查清单

- [ ] Task 1: 拆分 index_crud.py 和 file_converters.py
- [ ] Task 2: 拆分 graph_builder.py
- [ ] Task 3: 废弃 API 迁移（Prompt → PromptTemplate）
- [ ] Task 4: 添加响应模型
- [ ] 全部 46 个测试通过
- [ ] 无新的警告或错误

## 后续计划

P1 完成后，继续处理：
- P2: 补充单元测试（会话隔离、权限中间件、上传限制）
- P2: 添加 CI/CD（GitHub Actions + ruff + mypy + pytest）
- P3: 安全加固（文件上传限制、Cookie 配置）
- P3: ComposableGraph.from_indices 废弃 API 迁移（需要更多调研）
