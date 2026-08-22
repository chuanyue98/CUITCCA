import asyncio
import logging
import os
from pathlib import Path

import configs.load_env as load_env
from handlers.vector_store import (
    _get_client,
    build_index_from_collection,
    create_empty_index,
    delete_collection,
    get_or_create_collection,
    list_index_names,
)
from llama_index.core import Document, VectorStoreIndex
from utils.logger import customer_logger

indexes: list[VectorStoreIndex] = []
_indexes_lock = asyncio.Lock()
_index_locks: dict[str, asyncio.Lock] = {}
_index_locks_guard = asyncio.Lock()


async def _get_index_lock(index_id: str) -> asyncio.Lock:
    """获取指定索引的锁，使用 guard 锁防止 TOCTOU 竞争"""
    async with _index_locks_guard:
        if index_id not in _index_locks:
            _index_locks[index_id] = asyncio.Lock()
        return _index_locks[index_id]


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
                metadata = collection.metadata or {}
                index.summary = metadata.get('summary', '')
                indexes.append(index)
            except Exception as e:
                logging.error(f"Error loading index {name}: {e}")


def _ingest_and_persist(index: VectorStoreIndex, doc_file_path: str) -> None:
    """同步的摄取+落盘工作，供 asyncio.to_thread 卸载到线程池执行。

    用 ingestion_pipeline 的 IngestionPipeline（UPSERTS 策略）替代直接
    ``index.insert_nodes``：内容不变的重复上传会被跳过、内容变化的重传会
    原地更新，而不是无限堆积重复 chunk。docstore 是每个索引持久化到磁盘的
    "doc_id -> 内容 hash" 记录，不落盘的话这个去重记忆每次进程重启就丢了。

    **单文件上传路径必须把解析失败抛出来**：``ingest_files`` 是为"批量摄取
    一批文件"设计的，单个文件解析失败会被收进 ``IngestResult.parse_failures``
    然后继续处理下一个——这对批量场景是对的（不能让一个坏文件中断整批），
    但这里每次只处理一个文件，把结果丢掉就意味着"这个文件根本没进知识库"
    这件事完全没人知道，接口还照样返回 ``{"status": "inserted"}``。

    这不是假想的场景：``ALLOWED_EXTENSIONS`` 放开图片格式之后，一台没装
    OCR 可选依赖（``uv sync --extra ocr``，默认不装）的机器上传 .jpg 会走到
    ``ParserUnavailableError`` -> 被 ingest_files 吞掉 -> 用户看到上传成功、
    实际零节点写入。损坏的 .doc/.pdf 同理。改造前这些格式在白名单那一步就被
    400 拒掉，反而不会骗人——放开白名单如果不同时把失败抛上去，就是用一个
    静默失败换掉了一个明确失败。
    """
    from handlers.ingestion_pipeline import build_pipeline, ingest_files
    from handlers.parsers.types import DocumentParseError
    from handlers.vector_store import load_or_create_docstore, persist_docstore

    docstore = load_or_create_docstore(index.index_id)
    pipeline = build_pipeline(vector_store=index.vector_store, docstore=docstore)
    result = ingest_files([Path(doc_file_path)], pipeline)

    if result.documents_loaded == 0:
        if result.parse_failures:
            raise DocumentParseError(result.parse_failures[0][1])
        if result.unreadable_files:
            raise DocumentParseError(result.unreadable_files[0][1])
        if result.empty_files:
            raise DocumentParseError("文件解析成功但没有任何文本内容，未写入任何节点")
        raise DocumentParseError("摄取没有产出任何文档")

    persist_docstore(index.index_id, docstore)


async def insert_into_index(index: VectorStoreIndex, doc_file_path: str, skip_summary: bool = False):
    from handlers.graph_builder import summary_index

    lock = await _get_index_lock(index.index_id)
    async with lock:
        await asyncio.to_thread(_ingest_and_persist, index, doc_file_path)
        if not skip_summary:
            index.summary = await summary_index(index)
            _save_summary(index)


def _embed_qa_and_persist(index: VectorStoreIndex, qa_pairs: list) -> None:
    """同步的 QA 摄取+落盘工作，供 asyncio.to_thread 卸载到线程池执行。

    原实现直接 ``index.insert_nodes(docs)``，doc_id 是 ``f"{id}_{i//2}"``
    这种自增序号，完全绕开了 ``ingestion_pipeline.build_pipeline`` 那套
    IngestionPipeline（UPSERTS 策略）+ 持久化 docstore 去重链路——同一份问答
    对第二次导入会拿到新的序号（除非调用方每次都传相同的 ``id`` 且顺序完全
    一致），管道判断不出"这是重复内容"，只会无限堆积重复分块。这不是假想的
    问题：``campus`` 索引现在 1537 个 chunk 里 716 个（46.6%）是完全重复内容，
    就是这条老路径长期运行的结果。

    改法是和文件上传路径（``_ingest_and_persist``）走同一条链路：
    ``load_or_create_docstore`` -> ``build_pipeline(vector_store=...,
    docstore=...)`` -> ``pipeline.run`` -> ``persist_docstore``。同时把每条
    QA 文档的 ``id_`` 从自增序号改成 ``content_hash(f"{q} {a}")``——这样
    "同样的问答对无论第几次导入、无论调用方传不传 id"都会被 UPSERTS 判定成
    同一份文档，内容不变就跳过，不重新嵌入。

    ``id`` 参数因此不再参与 doc_id 的生成，但入参签名保留不变（
    ``embeddingQA`` 的调用方 ``router/index.py`` 不用跟着改）。
    """
    from handlers.ingestion_pipeline import build_pipeline, content_hash
    from handlers.vector_store import load_or_create_docstore, persist_docstore

    docs = []
    for i in range(0, len(qa_pairs), 2):
        q = qa_pairs[i]
        if i + 1 < len(qa_pairs):
            a = qa_pairs[i + 1]
            text = f"{q} {a}"
            doc = Document(text=text, id_=content_hash(text))
            customer_logger.info(f"{doc.text}")
            docs.append(doc)

    if not docs:
        return

    docstore = load_or_create_docstore(index.index_id)
    pipeline = build_pipeline(vector_store=index.vector_store, docstore=docstore)
    pipeline.run(documents=docs)
    persist_docstore(index.index_id, docstore)


async def embeddingQA(index: VectorStoreIndex, qa_pairs: list, id: str | None = None):
    lock = await _get_index_lock(index.index_id)
    async with lock:
        await asyncio.to_thread(_embed_qa_and_persist, index, qa_pairs)
        _save_summary(index)


def get_all_docs(index: VectorStoreIndex, limit: int = 0, offset: int = 0) -> list[dict]:
    try:
        client = _get_client()
        collection = client.get_collection(index.index_id)
        kwargs = {}
        if limit > 0:
            kwargs['limit'] = limit
        if offset > 0:
            kwargs['offset'] = offset
        data = collection.get(**kwargs)
        if not data or not data.get('ids'):
            return []
        docs = [
            {
                "doc_id": (data['metadatas'][i] or {}).get('ref_doc_id', '') if data.get('metadatas') else '',
                "node_id": data['ids'][i],
                "text": data['documents'][i] if data.get('documents') else '',
            }
            for i in range(len(data['ids']))
        ]
        return sorted(docs, key=lambda x: x["doc_id"])
    except Exception as e:
        logging.error(f"Error getting docs from ChromaDB: {e}")
        return []


def updateNodeById(index: VectorStoreIndex, id_: str, text: str):
    client = _get_client()
    collection = client.get_collection(index.index_id)
    data = collection.get(ids=[id_])
    if not data or not data['ids']:
        raise KeyError(f"node_id {id_} not found")
    from llama_index.core import Settings
    emb = Settings.embed_model.get_text_embedding(text)
    collection.update(ids=[id_], documents=[text], embeddings=[emb])


def deleteNodeById(index: VectorStoreIndex, id_: str):
    client = _get_client()
    collection = client.get_collection(index.index_id)
    data = collection.get(ids=[id_])
    if not data or not data['ids']:
        raise KeyError(f"node_id {id_} not found")
    collection.delete(ids=[id_])


def deleteDocById(index: VectorStoreIndex, doc_id: str):
    client = _get_client()
    collection = client.get_collection(index.index_id)
    try:
        data = collection.get(where={"ref_doc_id": doc_id})
    except Exception:
        data = collection.get()
        if not data or not data['ids']:
            return
        ids_to_delete = [
            data['ids'][i]
            for i in range(len(data['ids']))
            if (data['metadatas'][i] or {}).get('ref_doc_id') == doc_id
        ]
    else:
        ids_to_delete = data.get('ids', []) if data else []

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)


def saveIndex(index: VectorStoreIndex):
    _save_summary(index)


def _save_summary(index: VectorStoreIndex):
    collection = get_or_create_collection(index.index_id)
    summary_val = getattr(index, 'summary', '')
    collection.modify(metadata={"summary": summary_val or ''})


def get_index_by_name(index_name: str) -> VectorStoreIndex | None:
    result: VectorStoreIndex | None = None
    for i in indexes:
        if i.index_id == index_name:
            result = i
            break
    return result


async def get_index_by_name_async(index_name: str) -> VectorStoreIndex | None:
    async with _indexes_lock:
        for i in indexes:
            if i.index_id == index_name:
                return i
    return None


async def convert_index_to_file(index_name: str, file_name: str):
    import aiofiles
    path = os.path.join(load_env.FILE_PATH, file_name)
    if not os.path.exists(load_env.FILE_PATH):
        os.makedirs(load_env.FILE_PATH)

    index = get_index_by_name(index_name)
    if index is None:
        return

    text_list = []
    for doc in index.docstore.docs.values():
        node_text = getattr(doc, 'text', None) or doc.get_content()
        if node_text:
            node_text = node_text.strip().replace('\n', '').replace('\r', '')
            text_list.append(node_text)

    async with aiofiles.open(path, 'w', encoding='utf-8') as f:
        await f.write('\n'.join(text_list))


async def citf(index: VectorStoreIndex, name: str):
    import aiofiles
    path = os.path.join(load_env.FILE_PATH, name)
    if not os.path.exists(load_env.FILE_PATH):
        os.makedirs(load_env.FILE_PATH)

    text_list = []
    for node_id, node_data in index.docstore.docs.items():
        node_text = getattr(node_data, 'text', None) or node_data.get_content()
        node_text = node_text.strip().replace('\n', '').replace('\r', '')
        text_list.append(node_text)

    async with aiofiles.open(path, 'w', encoding='utf-8') as f:
        await f.write('\n'.join(text_list))


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
    if docs_list is None:
        return []
    docs = index.docstore.get_nodes(docs_list.node_ids)
    return docs
