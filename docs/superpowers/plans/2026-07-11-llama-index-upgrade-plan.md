# CUITCCA LlamaIndex 升级改造实施计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 按任务逐步执行。步骤使用 `- [ ]` 跟踪进度。

**Goal:** 升级 LlamaIndex 至最新稳定版，替换弃用 API，以 Chroma 替代文件级 JSON 持久化，清理死代码和修复已知 Bug。

**Architecture:** 保持 FastAPI + 路由模式不变。向量存储从文件 JSON 切换为 Chroma。查询引擎从 ComposableGraph 切换为 RouterQueryEngine。全局 Settings 模式保留。

**Tech Stack:** Python 3.12+, llama-index-core, chromadb, llama-index-vector-stores-chroma, llama-index-embeddings-huggingface (bge-m3), llama-index-llms-openai-like

## Global Constraints

- Python >= 3.12
- Embedding 模型: `BAAI/bge-m3`
- LLM: OpenAILike (OpenAI API / 第三方兼容 API)
- 测试通过: `python -m unittest discover -s tests -v`
- Chroma 持久化目录: `data/chroma_db/`
- 不迁移旧数据，从头重建索引

---

### Task 1: 依赖调整 & LLM 配置更新

**Files:**
- Modify: `pyproject.toml`
- Modify: `backend/app/configs/load_env.py`
- Modify: `backend/app/configs/llm_predictor.py`
- Delete: `backend/app/configs/embed_model.py`

**Interfaces:**
- Consumes: 无
- Produces: 更新后的依赖和配置，`CHROMA_DB_PATH` 环境变量

- [ ] **Step 1: 更新 pyproject.toml 依赖**

将 `pyproject.toml` 的 dependencies 改为：

```toml
dependencies = [
    "fastapi>=0.139.0",
    "uvicorn>=0.50.2",
    "python-dotenv>=1.1.0",
    "python-multipart>=0.0.32",
    "pydantic[email]>=2.9.0",
    "aiofiles>=24.1.0",
    "openai>=2.45.0",
    "llama-index-core>=0.15.0",
    "llama-index-embeddings-huggingface>=0.5.0",
    "llama-index-llms-openai-like>=0.4.0",
    "llama-index-vector-stores-chroma>=0.3.0",
    "chromadb>=0.6.0",
    "requests>=2.34.2",
    "pandas>=2.2.3",
    "python-docx>=1.1.0",
    "pdfplumber>=0.11.10",
    "tiktoken>=0.13.0",
    "orjson>=3.11.9",
    "PyYAML>=6.0.3",
    "networkx>=3.6.1",
    "xlrd>=2.0.2",
    "XlsxWriter>=3.2.9",
    "tqdm>=4.68.3",
]
```

移除: `langchain`, `langchain-community`, `langchain-text-splitters`, `llama-index-readers-file`, `llama-index-llms-openai`

- [ ] **Step 2: 清理 `load_env.py`**

删除 `import openai`、`openai.api_key` 和 `openai.api_base` 赋值。新增 `chroma_db_path`。修改后：

```python
import os
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

index_save_directory = ''
SAVE_PATH = ''
LOAD_PATH = ''
FEEDBACK_PATH = ''
LOG_PATH = ''
FILE_PATH = ''
access_stats_path = ''
openai_api_key = ''
openai_api_base = ''
openai_model = ''
VERBOSE = False
chroma_db_path = ''


def reload_env_variables():
    load_dotenv(os.path.join(os.path.dirname(PROJECT_ROOT), '.env'), override=True)
    global index_save_directory, SAVE_PATH, LOAD_PATH, FEEDBACK_PATH, LOG_PATH, FILE_PATH, access_stats_path, \
        openai_api_key, openai_api_base, openai_model, VERBOSE, COOKIE_SECURE, COOKIE_MAX_AGE, chroma_db_path

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    openai_api_base = os.environ.get('OPENAI_API_BASE') or 'https://api.openai.com/v1'
    openai_model = os.environ.get('OPENAI_MODEL', 'sensenova-6.7-flash-lite')
    VERBOSE = os.environ.get('VERBOSE', 'False').lower() in ('true', '1', 't')

    index_save_directory = os.environ.get('INDEX_SAVE_DIRECTORY', '../../data/indexes/')
    SAVE_PATH = os.environ.get('SAVE_PATH', '../../data/upload_files')
    LOAD_PATH = os.environ.get('LOAD_PATH', '../../data/temp/')
    FEEDBACK_PATH = os.environ.get('FEEDBACK_PATH', '../../feedback/')
    LOG_PATH = os.environ.get('LOG_PATH', '../../log/')
    FILE_PATH = os.environ.get('FILE_PATH', '../../data/export/')
    chroma_db_path = os.environ.get('CHROMA_DB_PATH', '../../data/chroma_db/')

    index_save_directory = os.path.join(PROJECT_ROOT, index_save_directory)
    SAVE_PATH = os.path.join(PROJECT_ROOT, SAVE_PATH)
    LOAD_PATH = os.path.join(PROJECT_ROOT, LOAD_PATH)
    FEEDBACK_PATH = os.path.join(PROJECT_ROOT, FEEDBACK_PATH)
    LOG_PATH = os.path.join(PROJECT_ROOT, LOG_PATH)
    FILE_PATH = os.path.join(PROJECT_ROOT, FILE_PATH)
    chroma_db_path = os.path.join(PROJECT_ROOT, chroma_db_path)
    access_stats_path = os.path.join(PROJECT_ROOT, '../access_stats.json')
    global COOKIE_SECURE, COOKIE_MAX_AGE
    COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'False').lower() in ('true', '1', 't')
    COOKIE_MAX_AGE = int(os.environ.get('COOKIE_MAX_AGE', '86400'))


MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.csv', '.xlsx'}
COOKIE_SECURE = False
COOKIE_MAX_AGE = 86400

reload_env_variables()
```

- [ ] **Step 3: 更新 `llm_predictor.py` Embedding 模型**

将 `DMetaSoul/Dmeta-embedding-zh-small` 改为 `BAAI/bge-m3`，设置 `trust_remote_code=True`（bge-m3 需要）：

```python
Settings.embed_model = HuggingFaceEmbedding(
    model_name="BAAI/bge-m3",
    device=device,
    normalize=True,
    trust_remote_code=True,
)
```

完整文件变更：

```python
from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.openai_like import OpenAILike
import torch

import configs.load_env as env_config

_CONTEXT_WINDOWS = {
    'sensenova-6.7-flash-lite': 262144,
    'deepseek-v4-flash': 1048576,
    'glm-5.2': 1048576,
    'sensenova-u1-fast': 262144,
}
_DEFAULT_CONTEXT_WINDOW = 32768
_MAX_TOKENS = 4096


def build_llm() -> OpenAILike:
    model = env_config.openai_model
    return OpenAILike(
        model=model,
        api_key=env_config.openai_api_key,
        api_base=env_config.openai_api_base,
        is_chat_model=True,
        context_window=_CONTEXT_WINDOWS.get(model, _DEFAULT_CONTEXT_WINDOW),
        max_tokens=_MAX_TOKENS,
    )


def init_settings():
    if Settings.embed_model is None or not isinstance(Settings.embed_model, HuggingFaceEmbedding):
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        Settings.embed_model = HuggingFaceEmbedding(
            model_name="BAAI/bge-m3",
            device=device,
            normalize=True,
            trust_remote_code=True,
        )
    if Settings.llm is None or not isinstance(Settings.llm, OpenAILike):
        Settings.llm = build_llm()
    if Settings.text_splitter is None:
        Settings.text_splitter = SentenceSplitter.from_defaults(chunk_size=512)


if __name__ == '__main__':
    init_settings()
    print(Settings.llm.complete('hi'))
```

- [ ] **Step 4: 删除 `embed_model.py`**

删除文件 `backend/app/configs/embed_model.py`。

- [ ] **Step 5: 安装新依赖并确认**

Run: `uv sync`

- [ ] **Step 6: 运行现有测试确认基线通过**

```bash
python -m unittest discover -s tests -v
```

Expected: 部分测试可能因依赖变更失败，记录失败项供后续修复。

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml backend/app/configs/load_env.py backend/app/configs/llm_predictor.py
git rm backend/app/configs/embed_model.py
git commit -m "build: update deps, switch to bge-m3 embedding, add chroma config"
```

---

### Task 2: Chroma 向量存储封装

**Files:**
- Create: `backend/app/handlers/vector_store.py`
- Modify: `backend/app/handlers/__init__.py`

**Interfaces:**
- Consumes: `configs.load_env.chroma_db_path`, `llama_index.core.Settings`
- Produces: `get_chroma_client()`, `get_or_create_collection(name)`, `list_index_names()`, `delete_collection(name)`, `build_index_from_collection(collection)`

- [ ] **Step 1: 创建 `handlers/vector_store.py`**

```python
import chromadb
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.chroma import ChromaVectorStore

from configs.load_env import chroma_db_path

_client_instance = None


def _get_client():
    global _client_instance
    if _client_instance is None:
        _client_instance = chromadb.PersistentClient(path=chroma_db_path)
    return _client_instance


def get_or_create_collection(name: str):
    client = _get_client()
    return client.get_or_create_collection(name)


def list_index_names() -> list[str]:
    client = _get_client()
    return [c.name for c in client.list_collections()]


def delete_collection(name: str):
    client = _get_client()
    client.delete_collection(name)


def build_index_from_collection(collection) -> VectorStoreIndex:
    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=Settings.embed_model,
    )
    return index


def create_empty_index(index_name: str) -> VectorStoreIndex:
    collection = get_or_create_collection(index_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=Settings.embed_model,
    )
    index.set_index_id(index_name)
    return index
```

- [ ] **Step 2: 运行导入检查**

```bash
cd backend && python -c "from handlers.vector_store import get_or_create_collection; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 测试 Chroma 基本功能**

```bash
cd backend && python -c "
from handlers.vector_store import create_empty_index, list_index_names, delete_collection
idx = create_empty_index('test-temp')
print('created:', idx.index_id)
print('list:', list_index_names())
delete_collection('test-temp')
print('after delete:', list_index_names())
print('OK')
"
```

Expected: 创建和删除正常

- [ ] **Step 4: 提交**

```bash
git add backend/app/handlers/vector_store.py
git commit -m "feat: add chroma vector store wrapper"
```

---

### Task 3: Index CRUD 重构 (文件持久化 → Chroma)

**Files:**
- Modify: `backend/app/handlers/index_crud.py`
- Modify: `backend/app/handlers/llama_handler.py`
- Delete: `backend/app/handlers/file_converters.py`
- Modify: `backend/app/main.py` (更新目录创建逻辑)

**Interfaces:**
- Consumes: `handlers/vector_store` 中的函数
- Produces: 通过 Chroma 操作的 `createIndex`, `loadAllIndexes`, `saveIndex`, `get_all_docs` 等

- [ ] **Step 1: 重写 `index_crud.py`**

```python
import asyncio
import logging
import os
import uuid

from llama_index.core import VectorStoreIndex, Document

from configs.load_env import FILE_PATH
from handlers.vector_store import (
    create_empty_index,
    build_index_from_collection,
    list_index_names,
    delete_collection,
    get_or_create_collection,
)
from utils.file import get_folders_list
from utils.logger import customer_logger

indexes: list[VectorStoreIndex] = []
_indexes_lock = asyncio.Lock()


def createIndex(index_name: str):
    index = create_empty_index(index_name)
    index.set_index_id(index_name)
    logging.info(f"index created: {index_name}")


async def loadAllIndexes():
    from configs.llm_predictor import init_settings
    init_settings()
    async with _indexes_lock:
        indexes.clear()
        for name in list_index_names():
            try:
                collection = get_or_create_collection(name)
                index = build_index_from_collection(collection)
                index.set_index_id(name)
                # Load summary from collection metadata
                metadata = collection.metadata or {}
                index.summary = metadata.get('summary', '')
                indexes.append(index)
            except Exception as e:
                logging.error(f"Error loading index {name}: {e}")


async def insert_into_index(index: VectorStoreIndex, doc_file_path: str):
    from handlers.graph_builder import summary_index
    from utils.llama import get_nodes_from_file

    async with _indexes_lock:
        nodes = get_nodes_from_file(doc_file_path)
        index.insert_nodes(nodes)
        index.summary = await summary_index(index)
        _save_summary(index)


def embeddingQA(index: VectorStoreIndex, qa_pairs: list, id: str | None = None):
    from handlers.graph_builder import summary_index
    if id is None:
        id = str(uuid.uuid4())

    docs = []
    for i in range(0, len(qa_pairs), 2):
        q = qa_pairs[i]
        if i + 1 < len(qa_pairs):
            a = qa_pairs[i + 1]
            doc = Document(text=f"{q} {a}", id_=id)
            customer_logger.info(f"{doc.text}")
            docs.append(doc)

    index.insert_nodes(docs)
    _save_summary(index)


def get_all_docs(index: VectorStoreIndex) -> list[dict]:
    docs = [
        {"doc_id": doc.ref_doc_id, "node_id": doc.node_id, "text": doc.get_content()}
        for doc in index.docstore.docs.values()
    ]
    return sorted(docs, key=lambda x: x["doc_id"])


def updateNodeById(index: VectorStoreIndex, id_: str, text: str):
    node = index.docstore.docs[id_]
    node.set_content(text)
    index.docstore.add_documents([node])


def deleteNodeById(index: VectorStoreIndex, id_: str):
    index.docstore.delete_document(id_)
    if hasattr(index, 'index_struct') and hasattr(index.index_struct, 'nodes_dict'):
        if id_ in index.index_struct.nodes_dict:
            del index.index_struct.nodes_dict[id_]


def deleteDocById(index: VectorStoreIndex, doc_id: str):
    index.delete_ref_doc(doc_id, delete_from_docstore=True)


def saveIndex(index: VectorStoreIndex):
    _save_summary(index)


def _save_summary(index: VectorStoreIndex):
    collection = get_or_create_collection(index.index_id)
    summary_val = getattr(index, 'summary', '')
    collection.modify(metadata={"summary": summary_val or ''})


def get_index_by_name(index_name: str) -> VectorStoreIndex | None:
    index: VectorStoreIndex = None
    for i in indexes:
        if i.index_id == index_name:
            index = i
            break
    return index


def convert_index_to_file(index_name: str, file_name: str):
    """通过索引名称将索引中的文本提取出来，存入一个txt文件中"""
    path = os.path.join(FILE_PATH, file_name)
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)

    index = get_index_by_name(index_name)
    if index is None:
        return

    text_list = []
    for doc in index.docstore.docs.values():
        node_text = getattr(doc, 'text', None) or doc.get_content()
        if node_text:
            node_text = node_text.strip().replace('\n', '').replace('\r', '')
            text_list.append(node_text)

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text_list))


def citf(index: VectorStoreIndex, name: str):
    path = os.path.join(FILE_PATH, name)
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)

    text_list = []
    for node_id, node_data in index.docstore.docs.items():
        node_text = getattr(node_data, 'text', None) or node_data.get_content()
        node_text = node_text.strip().replace('\n', '').replace('\r', '')
        text_list.append(node_text)

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text_list))


def format_source_nodes_list(node_with_score_list):
    formatted_nodes = []
    for node_with_score in node_with_score_list:
        formatted_node = {
            'id': node_with_score.node.id_,
            'text': node_with_score.node.text
        }
        formatted_nodes.append(formatted_node)
    return formatted_nodes


def delete_index(index_name: str):
    delete_collection(index_name)


def get_docs_from_index(index: VectorStoreIndex, doc_id: str):
    docs_list = index.docstore.get_ref_doc_info(doc_id)
    docs = index.docstore.get_nodes(docs_list.node_ids)
    return docs
```

- [ ] **Step 2: 更新 `llama_handler.py`**

删除 `file_converters` 导入，更新导入路径：

```python
from handlers.index_crud import (
    indexes,
    _indexes_lock,
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
    convert_index_to_file,
    citf,
    format_source_nodes_list,
    delete_index,
    get_docs_from_index,
)
from handlers.graph_builder import (
    compose_graph_chat_egine,
    compose_graph_query_engine,
    summary_index,
    get_history_msg,
)
```

- [ ] **Step 3: 删除 `file_converters.py`**

```bash
git rm backend/app/handlers/file_converters.py
```

- [ ] **Step 4: 更新 `main.py` 中的目录创建逻辑**

在 `lifespan` 中移除 `index_save_directory`，改为 `chroma_db_path`：

```python
from configs.load_env import chroma_db_path, SAVE_PATH, LOAD_PATH, access_stats_path, reload_env_variables, COOKIE_SECURE, COOKIE_MAX_AGE

@asynccontextmanager
async def lifespan(app: FastAPI):
    reload_env_variables()
    init_settings()
    await loadAllIndexes()
    for directory in [SAVE_PATH, LOAD_PATH, chroma_db_path]:
        if not os.path.exists(directory):
            os.makedirs(directory)
    # ... rest unchanged
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/handlers/index_crud.py backend/app/handlers/llama_handler.py backend/app/main.py
git rm backend/app/handlers/file_converters.py
git commit -m "refactor(index): migrate vector store from file JSON to Chroma"
```

---

### Task 4: Graph Builder 重构 (ComposableGraph → RouterQueryEngine)

**Files:**
- Modify: `backend/app/handlers/graph_builder.py`
- Modify: `backend/app/router/graph.py`

**Interfaces:**
- Consumes: `indexes` 和 `_indexes_lock` from `index_crud`, `Prompts` from `configs.config`, `generate_query_engine_tools` from `utils.llama`
- Produces: `compose_graph_chat_egine()`, `compose_graph_query_engine()`, `summary_index()`

- [ ] **Step 1: 重写 `graph_builder.py`**

```python
import re
import logging

from llama_index.core import VectorStoreIndex
from llama_index.core.chat_engine import CondenseQuestionChatEngine
from llama_index.core.chat_engine.types import BaseChatEngine
from llama_index.core.indices.query.base import BaseQueryEngine
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.selectors.pydantic_selectors import PydanticMultiSelector
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from configs.config import Prompts
from configs.load_env import VERBOSE
from handlers.index_crud import indexes, _indexes_lock


def _build_router_query_engine(
    streaming: bool = False,
) -> RouterQueryEngine:
    query_engine_tools = []
    for index in indexes:
        engine = index.as_query_engine(
            streaming=streaming,
            text_qa_template=Prompts.QA_PROMPT.value,
            refine_template=Prompts.REFINE_PROMPT.value,
            similarity_top_k=3,
            verbose=VERBOSE,
        )
        tool = QueryEngineTool(
            query_engine=engine,
            metadata=ToolMetadata(
                name=index.index_id,
                description=getattr(index, 'summary', '') or index.index_id,
            ),
        )
        query_engine_tools.append(tool)

    query_engine = RouterQueryEngine(
        selector=PydanticMultiSelector.from_defaults(),
        query_engine_tools=query_engine_tools,
        verbose=VERBOSE,
    )
    return query_engine


async def compose_graph_chat_egine() -> BaseChatEngine:
    async with _indexes_lock:
        _indexes_snapshot = list(indexes)

    query_engine = _build_router_query_engine(streaming=True)

    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=query_engine,
        condense_question_prompt=Prompts.CONDENSE_QUESTION_PROMPT.value,
        verbose=VERBOSE,
    )

    return chat_engine


def compose_graph_query_engine(streaming: bool = False) -> BaseQueryEngine:
    return _build_router_query_engine(streaming=streaming)


async def summary_index(index):
    summary = await index.as_query_engine(response_mode="tree_summarize").aquery(
        "总结，生成文章摘要，要覆盖所有要点，方便后续检索,不需要详细内容，只需要关键信息，方便后续检索")
    summary_str = re.sub(r"\s+", " ", str(summary))
    summary_str = re.sub(r"[^\w\s]", "", summary_str)
    logging.info(f"Summary: {summary_str}")
    return summary_str


def get_history_msg(chat_engine: BaseChatEngine):
    return chat_engine.chat_history
```

- [ ] **Step 2: 简化 `router/graph.py`**

删除对 `compose_graph_query_engine` 中已不存在的功能的引用（`custom_query_engines` 不再需要）。关键变更：

`/graph/query_stream` 和 `/graph/query` 端点现在使用 `compose_graph_query_engine()` 返回的 `RouterQueryEngine`。行为不变。

WebSocket 端点同样使用 `RouterQueryEngine`。

`/graph/create` 后续调用 `_build_router_query_engine` 替代 `ComposableGraph`。

无需修改 `router/graph.py` 的接口代码——它已经使用 `compose_graph_chat_egine()` 和 `compose_graph_query_engine()` 这两个函数名，接口不变。

但需要验证 `router/graph.py` 的导入——确认 `compose_graph_query_engine` 等从 `handlers.llama_handler` 引入的函数仍然存在。

`router/graph.py` 中的 `query_router` 端点已经是一个 `RouterQueryEngine` 示例，可作为参考。现在 `compose_graph_query_engine` 返回同样的类型，保持一致。

- [ ] **Step 3: 运行简单的导入和逻辑测试**

```bash
cd backend && python -c "
from handlers.graph_builder import compose_graph_query_engine, compose_graph_chat_egine, summary_index
print('graph_builder imports OK')
"
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/handlers/graph_builder.py
git commit -m "refactor(graph): replace ComposableGraph with RouterQueryEngine"
```

---

### Task 5: Bug 修复 & 死代码清理

**Files:**
- Modify: `backend/app/utils/llama.py`
- Modify: `backend/app/router/index.py`
- Modify: `backend/app/configs/__init__.py`

**Interfaces:**
- Consumes: 现有函数签名，需修复不规范调用
- Produces: 正确的 API 调用和清理后的导入

- [ ] **Step 1: 清理 `utils/llama.py`**

- 删除 `from langchain_core.messages import ChatMessage`（死引入）
- `SimpleNodeParser` → `SentenceSplitter`（已导入但未使用，改为使用）

```python
import asyncio
import json
import re
from typing import List, Any

from llama_index.core import SimpleDirectoryReader, Settings
from llama_index.core.indices.base import BaseIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.tools import QueryEngineTool

from configs.config import Prompts
from utils.logger import customer_logger


_DEFAULT_QA_INSTRUCTION = (
    "请根据以下内容生成尽可能多的问答对。\n"
    "要求：问题和答案都需完整详细。\n"
    "按下面格式返回：\n"
    "Q:\nA:\nQ:\nA:\n..."
)


def build_qa_generation_prompt(custom_prompt: str | None) -> str:
    return custom_prompt or _DEFAULT_QA_INSTRUCTION


def get_nodes_from_file(file_path):
    splitter = SentenceSplitter.from_defaults()
    documents = SimpleDirectoryReader(input_files=[file_path], filename_as_id=True).load_data()
    for doc in documents:
        doc.id_ = extract_content_after_backslash(doc.id_)
    return splitter.get_nodes_from_documents(documents)


def extract_content_after_backslash(string: str) -> str:
    return string.replace('\\', '/').rsplit('/', 1)[-1]


def formatted_pairs(qa_data_list):
    qa_pairs = []
    pattern = r'(?:Q: |A: )'
    for qa_data in qa_data_list:
        pairs = re.split(pattern, qa_data)
        pairs = [pair.strip() for pair in pairs if pair.strip()]
        qa_pairs.extend(pairs)
    return qa_pairs


async def generate_qa_batched(contents: str, prompt: str = None):
    contents = contents.replace("\n", "")
    contents = contents.strip()
    textSplitter = SentenceSplitter(chunk_size=1024)
    contents = textSplitter.split_text(contents)
    if prompt is None:
        prompt = "我会发送一段长文本"
    prompt = f"""   你是出题人。
                    {prompt}从中提取出若干个,尽可能多的问题和答案。 问题答案详完整详细,按下面格式返回:
                    Q:
                    A:
                    Q:
                    A:
                    ...
                """
    semaphore = asyncio.Semaphore(5)
    async def sem_complete(content):
        async with semaphore:
            return await Settings.llm.acomplete(prompt + content)
    tasks = [sem_complete(content) for content in contents]
    responses = await asyncio.gather(*tasks)
    qa_pairs = [res.text for res in responses if res]
    return qa_pairs


def generate_query_engine_tools(indexes: List[BaseIndex]) -> List[QueryEngineTool]:
    query_engine_tools = []
    for index in indexes:
        query_engine = index.as_query_engine(
            streaming=True,
            text_qa_template=Prompts.QA_PROMPT.value,
            refine_template=Prompts.REFINE_PROMPT.value,
        )
        description = index.summary
        tool = QueryEngineTool.from_defaults(query_engine=query_engine, description=description)
        query_engine_tools.append(tool)
    return query_engine_tools


if __name__ == '__main__':
    res = asyncio.run(generate_qa_batched(
        "本科招生http://zjc.cuit.edu.cn/Index.htm研究生招生https://yjsc.cuit.edu.cn/继续教育招生https://cjy.cuit.edu.cn/", ))
    print(res)
```

- [ ] **Step 2: 修复 `router/index.py` 中的 `ResponseEvaluator` 用法**

```python
@index_app.post("/{index_name}/evaluator")
async def evaluator(index=Depends(get_index), query: str = Form()):
    from llama_index.core.evaluation import ResponseEvaluator
    from configs.llm_predictor import build_llm

    llm = build_llm()
    evaluator = ResponseEvaluator(llm=llm)
    query_engine = index.as_query_engine()
    response = await query_engine.aquery(query)
    eval_result = await evaluator.aevaluate(response=response, query=query)
    return {"result": str(eval_result)}
```

- [ ] **Step 3: 修复 `router/index.py` 中的 `insert_docs` 端点**

将 `index.insert(doc)` 改为 `index.insert_nodes([doc])`：

```python
@index_app.post("/{index_name}/insertdoc")
async def insert_docs(text=Form(), doc_id=Form(None), index=Depends(get_index)):
    if doc_id is None:
        doc = Document(text=text)
    else:
        doc_id = doc_id.replace("\\\\", "\\")
        doc = Document(text=text, doc_id=doc_id)
    index.insert_nodes([doc])
    saveIndex(index)
    return {"status": "ok"}
```

- [ ] **Step 4: 更新 `configs/__init__.py`**

新增导出 `chroma_db_path`：

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
    chroma_db_path,
    reload_env_variables,
)
```

- [ ] **Step 5: 删除 `router/index.py` 中未使用的导入**

删除不再需要的导入：`import torch`, `from llama_index.embeddings.huggingface import HuggingFaceEmbedding`, `from llama_index.core.evaluation import ResponseEvaluator`（移到函数内部）

更新 `router/index.py` 顶部：

```python
import logging
import os
import shutil
import re
import uuid
from typing import List

import aiofiles
from fastapi import APIRouter, Form, File, UploadFile, status, Depends, HTTPException
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import Settings, Document
from starlette.responses import JSONResponse

from configs.config import Prompts
from configs.load_env import index_save_directory, SAVE_PATH, LOAD_PATH, PROJECT_ROOT, LOG_PATH
from configs.llm_predictor import build_llm, init_settings
from handlers.graph_builder import summary_index
from handlers.llama_handler import (
    _indexes_lock,
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
    citf,
)
from utils.logger import customer_logger
from dependencies import get_index
from models.response import IndexListResponse, QueryResponse, UploadResponse
from utils.file import read_file_contents, safe_filename, get_folders_list
from utils.llama import formatted_pairs, generate_qa_batched, extract_content_after_backslash, \
    build_qa_generation_prompt
from utils.upload import validate_upload_file, FileTooLargeError, InvalidFileTypeError
```

- [ ] **Step 6: 提交**

```bash
git add backend/app/utils/llama.py backend/app/router/index.py backend/app/configs/__init__.py
git commit -m "fix: SimpleNodeParser -> SentenceSplitter, fix ResponseEvaluator, cleanup dead code"
```

---

### Task 6: 测试更新 & 回归

**Files:**
- Modify: `tests/test_llama_handler.py`
- Modify: `tests/test_get_nodes_from_file.py`
- Create: `tests/test_chroma_store.py`

- [ ] **Step 1: 更新 `test_llama_handler.py`**

`test_llama_handler.py` 中的 `FakeIndex` 和 mock 测试主要测试逻辑逻辑而非存储层，只需确保 `assert_called_once_with` 中的路径参数改为 Chroma 调用。

`SaveIndexTest` 现在调用 `_save_summary` 写 Chroma collection metadata，mock 需要更新：

```python
class SaveIndexTest(unittest.TestCase):
    def setUp(self):
        patcher = patch('handlers.index_crud.get_or_create_collection')
        self.mock_get_or_create = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_collection = MagicMock()
        self.mock_get_or_create.return_value = self.mock_collection
        # Summary 需要 mock 异步 query
        self.summary_patcher = patch('handlers.index_crud.summary_index', new_callable=AsyncMock)
        self.mock_summary = self.summary_patcher.start()
        self.mock_summary.return_value = 'test summary'
        self.addCleanup(self.summary_patcher.stop)

    def test_saves_summary_to_collection_metadata(self):
        index = FakeIndex(index_id='myindex')
        index.summary = 'my summary'
        lh.saveIndex(index)
        self.mock_collection.modify.assert_called_once_with(
            metadata={"summary": "my summary"}
        )
```

完整更新 `test_llama_handler.py`：

```python
import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

import tests._pathsetup  # noqa: F401

import handlers.llama_handler as lh
import handlers.index_crud as index_crud


class FakeIndex:
    def __init__(self, index_id='test-index'):
        self.index_id = index_id
        self.inserted_docs = []
        self.docstore = MagicMock()


class LoadAllIndexesTest(unittest.TestCase):
    def setUp(self):
        lh.indexes.clear()
        self._orig_list_names = index_crud.list_index_names
        self._orig_build = index_crud.build_index_from_collection

        index_crud.list_index_names = MagicMock(return_value=['a', 'b'])
        mock_index = FakeIndex()
        index_crud.build_index_from_collection = MagicMock(return_value=mock_index)

    def tearDown(self):
        lh.indexes.clear()
        index_crud.list_index_names = self._orig_list_names
        index_crud.build_index_from_collection = self._orig_build

    def test_does_not_duplicate_on_repeated_calls(self):
        asyncio.run(lh.loadAllIndexes())
        self.assertEqual(len(lh.indexes), 2)

        asyncio.run(lh.loadAllIndexes())
        self.assertEqual(len(lh.indexes), 2, 'calling loadAllIndexes twice should not duplicate entries')


class EmbeddingQATest(unittest.TestCase):
    def test_two_calls_without_explicit_id_get_different_ids(self):
        index1 = FakeIndex()
        index2 = FakeIndex()

        lh.embeddingQA(index1, ['q1', 'a1'])
        lh.embeddingQA(index2, ['q2', 'a2'])

        id1 = index1.inserted_docs[0].id_
        id2 = index2.inserted_docs[0].id_
        self.assertNotEqual(id1, id2, 'each call without an explicit id must get a fresh uuid')


class SaveIndexTest(unittest.TestCase):
    def setUp(self):
        self.patcher = patch('handlers.index_crud.get_or_create_collection')
        self.mock_get_or_create = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.mock_collection = MagicMock()
        self.mock_get_or_create.return_value = self.mock_collection

    def test_saves_summary_to_collection_metadata(self):
        index = FakeIndex(index_id='myindex')
        index.summary = 'my summary'
        lh.saveIndex(index)
        self.mock_collection.modify.assert_called_once_with(
            metadata={"summary": "my summary"}
        )


class UpdateNodeByIdTest(unittest.TestCase):
    def test_persists_after_update(self):
        node = MagicMock()
        index = FakeIndex(index_id='myindex')
        index.docstore.docs = {'n1': node}

        lh.updateNodeById(index, 'n1', 'new text')

        node.set_content.assert_called_once_with('new text')
        index.docstore.add_documents.assert_called_once_with([node])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 更新 `test_get_nodes_from_file.py`**

确认 `SentenceSplitter` 取代 `SimpleNodeParser` 后的行为不变（接口一致）：

```python
import os
import tempfile
import unittest

import tests._pathsetup  # noqa: F401

import utils.llama as llama_utils


class GetNodesFromFileTest(unittest.TestCase):
    def test_loads_nodes_from_a_single_file_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, 'note.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("图书馆每天早上8点到晚上10点开放。")

            nodes = llama_utils.get_nodes_from_file(file_path)

        self.assertTrue(nodes)
        self.assertIn("图书馆", nodes[0].get_content())


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 3: 创建 `test_chroma_store.py`**

```python
import unittest
import tempfile
import os

import tests._pathsetup  # noqa: F401


class ChromaStoreBasicTest(unittest.TestCase):
    def setUp(self):
        # Save original path and override
        import handlers.vector_store as vs
        self._orig_client = vs._client_instance
        vs._client_instance = None
        self._tmp_dir = tempfile.mkdtemp()

        import configs.load_env as env
        self._orig_chroma_path = env.chroma_db_path
        env.chroma_db_path = self._tmp_dir

        # Reimport would be complex, just test via public API
        self.vs = vs

    def tearDown(self):
        self.vs._client_instance = self._orig_client
        import configs.load_env as env
        env.chroma_db_path = self._orig_chroma_path

    def test_create_and_list_collections(self):
        # Use the module directly with overridden path
        import chromadb
        client = chromadb.PersistentClient(path=self._tmp_dir)
        client.get_or_create_collection('test-col')
        names = [c.name for c in client.list_collections()]

        self.assertIn('test-col', names)

    def test_delete_collection(self):
        import chromadb
        client = chromadb.PersistentClient(path=self._tmp_dir)
        client.get_or_create_collection('to-delete')
        client.delete_collection('to-delete')
        names = [c.name for c in client.list_collections()]

        self.assertNotIn('to-delete', names)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 4: 运行全部测试**

```bash
python -m unittest discover -s tests -v
```

Expected: 除 `test_graph_state.py` 部分测试可能因 mock 对象变化需要调整外，其余测试通过。

记录具体失败项并修复。

- [ ] **Step 5: 修复 `test_graph_state.py`**

`test_graph_state.py` 通过 `_load_graph_module` 加载 `router/graph.py` 独立模块。只要 `graph.py` 的公共 API 函数名不变（`compose_graph_chat_egine`, `compose_graph_query_engine`），测试应继续工作。

需要确认 mock 的 `compose_graph_chat_egine` 和 `compose_graph_query_engine` 返回值类型兼容 `RouterQueryEngine`（它也是 `BaseQueryEngine` 子类）。

如果 `_make_fake_engine` 返回的 MagicMock 被 `RouterQueryEngine` 的方法调用，测试可能失败。修复方式：将 mock 的 `side_effect` 调整或直接用 AsyncMock 替代。

```python
# In test_graph_state.py, update _make_fake_engine:
def _make_fake_engine(self):
    engine = AsyncMock()
    fake_stream = MagicMock(response_gen=iter(['chunk']))
    engine.astream_chat = AsyncMock(return_value=fake_stream)
    return engine
```

- [ ] **Step 6: 最终全量回归测试**

```bash
python -m unittest discover -s tests -v
```

Expected: 所有测试通过。

- [ ] **Step 7: 提交**

```bash
git add tests/test_llama_handler.py tests/test_get_nodes_from_file.py tests/test_chroma_store.py tests/test_graph_state.py
git commit -m "test: update tests for Chroma, SentenceSplitter, and RouterQueryEngine"
```
