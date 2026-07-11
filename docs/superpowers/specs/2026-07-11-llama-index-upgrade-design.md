# CUITCCA LlamaIndex 升级改造设计

## 概述

对 CUITCCA 校园 AI 助手进行 LlamaIndex 升级和架构重构。当前使用 `llama-index-core>=0.14.23`，存在多项已弃用 API 和死代码，向量存储依赖脆弱的 JSON 文件持久化。

## 目标

- 升级至最新 LlamaIndex 稳定版
- 替换所有已弃用 API
- 以 Chroma 替代文件级 JSON 向量存储
- 清理无用依赖和死代码
- 修复已知并发 BUG

## 非目标

- 后端框架更换（保留 FastAPI）
- 前端改造（保留现有静态页面）
- 原有索引数据的迁移（重新构建）

## 详细变更

### 1. 依赖层 (pyproject.toml)

- 升级: `llama-index-core` → latest 稳定版
- 新增: `llama-index-vector-stores-chroma`, `chromadb`
- 保留: `llama-index-embeddings-huggingface`, `llama-index-llms-openai-like`
- 移除: `langchain`, `langchain-community`, `langchain-text-splitters`, `llama-index-readers-file`, `llama-index-llms-openai`

### 2. LLM 配置

- `load_env.py`: 删除 `openai.api_key`/`openai.api_base` 全局设置（对 OpenAILike 无效）
- `llm_predictor.py`: Settings 模式不变，Embedding 模型从 `DMetaSoul/Dmeta-embedding-zh-small` 替换为 `BAAI/bge-m3`

### 3. 向量存储 — Chroma 集成

- 新增 `handler/vector_store.py`: Chroma 客户端封装
- 索引存储从 `data/indexes/{name}/vector_store.json` 等 JSON 文件改为 Chroma 持久化目录 `data/chroma_db/`
- 索引名 ↔ Chroma collection 名一一对应
- `index_crud.py` 重构：
  - `create_index()`: `ChromaVectorStore` → `VectorStoreIndex.from_vector_store()`
  - `load_single_index()`: 通过 Chroma collection 重建
  - `save_index()` / `delete_index_directory()`: 改为 Chroma API
  - 删除 `file_converters.py`（JSON 直接修改逻辑，不再需要）

### 4. 查询引擎 — 替换 ComposableGraph

- `graph_builder.py` 重构：
  - `compose_graph_query_engine()`: ComposableGraph → RouterQueryEngine + PydanticMultiSelector
  - `build_graph_chat_engine()`: CondenseQuestionChatEngine 保留，去掉冗余 `chat_mode="condense_question"`
  - 单层 RouterQueryEngine 替代两层 root_graph + node_graph 结构
- `router/graph.py`: 简化路由逻辑，统一用 RouterQueryEngine + ReActAgent 两条路径

### 5. 已知 Bug 修复与死代码清理

| 问题 | 修复 |
|------|------|
| `SimpleNodeParser` 弃用 | 全换 `SentenceSplitter` |
| `index.insert()` / `insert_nodes()` 混用 | 统一用 `insert_nodes()` |
| `ResponseEvaluator` 参数缺失 | 传入 LLM，修正 `aevaluate(query, response)` 签名 |
| `ChatMessage` 死引入 | 删除 |
| `embed_model.py` 空文件 | 删除 |
| `_graph_chat_engines` / `indexes` 锁竞态 | `graph_builder.py` 中所有访问加 `_indexes_lock` |
| `get_response_synthesizer` 未使用返回值 | 删除或传入 `as_query_engine()` |
| `openai.api_key` / `api_base` 配置 | 删除 |

## 受影响文件清单

```
pyproject.toml
backend/app/configs/load_env.py
backend/app/configs/llm_predictor.py
backend/app/handlers/index_crud.py
backend/app/handlers/graph_builder.py
backend/app/handlers/file_converters.py        # 删除
backend/app/utils/llama.py
backend/app/router/index.py
backend/app/router/graph.py
backend/app/router/response.py
backend/app/router/test.py
[新增] backend/app/handlers/vector_store.py
```

## 测试策略

- 现有 unittest 全部通过（`python -m unittest discover -s tests -v`）
- `test_llama_handler.py`: 适配新的 Chroma 存储 API
- `test_get_nodes_from_file.py`: 确认 SentenceSplitter 行为
- `test_graph_state.py`: 验证 RouterQueryEngine 会话隔离
- `test_llm_predictor.py`: 确认 bge-m3 配置生效
- 新增 `test_chroma_store.py`: 验证 Chroma 增删改查

## 实施顺序

1. pyproject.toml 依赖调整 + 安装
2. Embedding 模型切换 (bge-m3)
3. Chroma 集成 (vector_store.py + index_crud.py 重构)
4. graph_builder.py 重构 (ComposableGraph → RouterQueryEngine)
5. 修复 Bug + 死代码清理
6. 测试回归
