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
