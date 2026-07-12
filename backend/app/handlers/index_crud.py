import asyncio
import logging
import os
import uuid

from configs.load_env import FILE_PATH
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


async def insert_into_index(index: VectorStoreIndex, doc_file_path: str, skip_summary: bool = False):
    from handlers.graph_builder import summary_index
    from utils.llama import get_nodes_from_file

    nodes = await asyncio.to_thread(get_nodes_from_file, doc_file_path)

    lock = await _get_index_lock(index.index_id)
    async with lock:
        await asyncio.to_thread(index.insert_nodes, nodes)
        if not skip_summary:
            index.summary = await summary_index(index)
            _save_summary(index)


async def embeddingQA(index: VectorStoreIndex, qa_pairs: list, id: str | None = None):
    if id is None:
        id = str(uuid.uuid4())

    docs = []
    for i in range(0, len(qa_pairs), 2):
        q = qa_pairs[i]
        if i + 1 < len(qa_pairs):
            a = qa_pairs[i + 1]
            doc_id = f"{id}_{i//2}"
            doc = Document(text=f"{q} {a}", id_=doc_id)
            customer_logger.info(f"{doc.text}")
            docs.append(doc)

    lock = await _get_index_lock(index.index_id)
    async with lock:
        await asyncio.to_thread(index.insert_nodes, docs)
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
    collection.update(ids=[id_], documents=[text])


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

    async with aiofiles.open(path, 'w', encoding='utf-8') as f:
        await f.write('\n'.join(text_list))


async def citf(index: VectorStoreIndex, name: str):
    import aiofiles
    path = os.path.join(FILE_PATH, name)
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)

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
