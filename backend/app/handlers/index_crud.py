import asyncio
import json
import logging
import os
import uuid

from llama_index.core import VectorStoreIndex, load_index_from_storage, StorageContext, Document
from llama_index.core.indices.base import BaseIndex

from configs.load_env import index_save_directory, FILE_PATH
from utils.file import get_folders_list
from utils.logger import customer_logger

indexes = []
_indexes_lock = asyncio.Lock()


def createIndex(index_name):
    """
    创建索引
    :param index_name: 索引名称
    :return:
    """
    index = VectorStoreIndex([])
    index.set_index_id(index_name)
    logging.info(f"index保存位置: {index_save_directory + index_name}")
    index.storage_context.persist(os.path.join(index_save_directory, index_name))


async def loadAllIndexes():
    """
    加载索引数据
    :param index_save_directory: 索引保存目录
    :return:
    """
    from configs.llm_predictor import init_settings
    init_settings()
    async with _indexes_lock:
        indexes.clear()
        for index_dir_name in get_folders_list(index_save_directory):
            # 获取索引目录的完整路径
            index_dir_path = os.path.join(index_save_directory, index_dir_name)
            try:
                storage_context = StorageContext.from_defaults(persist_dir=index_dir_path)
                index = load_index_from_storage(storage_context)
                # Load summary if summary.txt exists
                summary_path = os.path.join(index_dir_path, 'summary.txt')
                if os.path.exists(summary_path):
                    with open(summary_path, 'r', encoding='utf-8') as f:
                        index.summary = f.read().strip()
                else:
                    index.summary = ""
                indexes.append(index)
            except Exception as e:
                logging.error(f"Error loading index {index_dir_name}: {e}")


async def insert_into_index(index, doc_file_path):
    """
    通过文档路径插入index
    :param index: 索引
    :param doc_file_path: 文档路径
    :param input_files 文档列表
    :return:
    """

    nodes = get_nodes_from_file(doc_file_path)
    index.insert_nodes(nodes)

    # 生成summary maxRecursion
    index.summary = await summary_index(index)
    saveIndex(index)


def embeddingQA(index: BaseIndex, qa_pairs, id=None):
    """
    将拆分后的问答对插入索引
    :param index: 索引
    :param qa_pairs: 问答对
    :param id: 文档id
    :return:
    """
    from handlers.graph_builder import summary_index
    if id is None:
        id = str(uuid.uuid4())

    for i in range(0, len(qa_pairs), 2):
        q = qa_pairs[i]
        if i + 1 < len(qa_pairs):
            a = qa_pairs[i + 1]
            doc = Document(text=f"{q} {a}", id_=id)
            customer_logger.info(f"{doc.text}")
            index.insert(doc)
        else:
            customer_logger.info(f"Last element': {qa_pairs[i]}")
    saveIndex(index)


def get_all_docs(index):
    """
    通过index，获取所有文档
    :param index:
    :return:
    """
    docs = [
        {"doc_id": doc.ref_doc_id, "node_id": doc.node_id, "text": doc.get_content()}
        for doc in index.docstore.docs.values()
    ]
    sorted_docs = sorted(docs, key=lambda x: x["doc_id"])
    return sorted_docs


def updateNodeById(index_, id_, text):
    """
    :param index_: 索引
    :param id_: node_id
    :param text: 更改后的内容
    :return:
    """
    # node = index.docstore.get_node(id_)
    node = index_.docstore.docs[id_]
    node.set_content(text)
    index_.docstore.add_documents([node])
    saveIndex(index_)


def deleteNodeById(index, id_):
    """
    删除时会自动保存修改到本地
    :param index: 索引
    :param id_: node_id
    :return:
    """
    index.docstore.delete_document(id_)
    # Also delete node from index struct in memory
    if hasattr(index, 'index_struct') and hasattr(index.index_struct, 'nodes_dict'):
        if id_ in index.index_struct.nodes_dict:
            del index.index_struct.nodes_dict[id_]
    # Delete from in-memory SimpleVectorStore if applicable
    if hasattr(index, 'vector_store') and hasattr(index.vector_store, '_data'):
        data = index.vector_store._data
        if hasattr(data, 'embedding_dict') and id_ in data.embedding_dict:
            del data.embedding_dict[id_]
        if hasattr(data, 'text_id_to_ref_doc_id') and id_ in data.text_id_to_ref_doc_id:
            del data.text_id_to_ref_doc_id[id_]
    saveIndex(index)


def deleteDocById(index, id):
    """
    # 删除文档 删除时会自动保存修改到本地
    :param id: 文档的id
    :return:
    """
    index.delete_ref_doc(id, delete_from_docstore=True)
    saveIndex(index)


def saveIndex(index):
    persist_dir = os.path.join(index_save_directory, index.index_id)
    index.storage_context.persist(persist_dir)
    # Persist index.summary to summary.txt
    summary_path = os.path.join(persist_dir, 'summary.txt')
    summary_val = getattr(index, 'summary', '')
    if summary_val:
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary_val)


def get_index_by_name(index_name):
    index: VectorStoreIndex = None
    for i in indexes:
        if i.index_id == index_name:
            index = i
            break
    return index


def convert_index_to_file(index_name, file_name):
    """通过索引名称将索引中的文本提取出来，存入一个txt文件中"""
    path = os.path.join(index_save_directory, index_name, 'docstore.json')
    out_path = os.path.join(FILE_PATH, file_name)
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    text_list = []
    for node_id, node_data in data['docstore/data'].items():
        node_text = node_data['__data__']['text']
        if node_text is not None:
            # 去除空格和换行符
            node_text = node_text.strip().replace('\n', '').replace('\r', '')
            text_list.append(node_text)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text_list))


def citf(index, name):
    """将index转换为file"""
    path = os.path.join(FILE_PATH, name)
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)
    data = index.docstore.docs
    text_list = []
    for node_id, node_data in data.items():
        node_text = getattr(node_data, 'text', None) or getattr(node_data, 'get_content', lambda: '')()
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


def fix_doc_id_not_found(index, doc_id):
    """
    修复文档id不存在的情况
    ‘ 删除后prev_node引用并没有删除
    """
    path = os.path.join(index_save_directory, index.index_id)
    remove_index_store(os.path.join(path, 'index_store.json'), doc_id)
    remove_vector_store(os.path.join(path, 'vector_store.json'), doc_id)
    remove_docstore(os.path.join(path, 'docstore.json'), doc_id)


def get_docs_from_index(index, doc_id):
    docs_list = index.docstore.get_ref_doc_info(doc_id)
    docs = index.docstore.get_nodes(docs_list.node_ids)
    return docs
