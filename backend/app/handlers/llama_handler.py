import json
import os
import re
import logging

import openai
from langchain.chat_models import ChatOpenAI
from llama_index import VectorStoreIndex, load_index_from_storage, StorageContext, ServiceContext, \
    SimpleDirectoryReader, LLMPredictor, ComposableGraph, ListIndex, Prompt, QuestionAnswerPrompt
from llama_index.chat_engine import CondenseQuestionChatEngine
from llama_index.chat_engine.types import BaseChatEngine
from llama_index.indices.base import BaseIndex
from llama_index.indices.query.base import BaseQueryEngine

from configs.config import Prompts
from configs.load_env import index_save_directory, FILE_PATH
from utils.llama import get_nodes_from_file
from utils.file import get_folders_list

indexes = []


def init():
    """
    创建所需文件夹
    :return:
    """
    if not os.path.exists(index_save_directory):
        os.makedirs(index_save_directory)


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


def loadAllIndexes():
    """
    加载索引数据
    :param index_save_directory: 索引保存目录
    :return:
    """
    for index_dir_name in get_folders_list(index_save_directory):
        # 获取索引目录的完整路径
        index_dir_path = os.path.join(index_save_directory, index_dir_name)
        storage_context = StorageContext.from_defaults(persist_dir=index_dir_path)
        index = load_index_from_storage(storage_context)
        indexes.append(index)




def insert_into_index(index, doc_file_path):
    """
    通过文档路径插入index
    :param index: 索引
    :param doc_file_path: 文档路径
    :param input_files 文档列表
    :return:
    """
    # 使用中文解析器解析文档
    llm_predictor = LLMPredictor(
        llm=ChatOpenAI(temperature=0.1, model_name="gpt-3.5-turbo-16k", max_tokens=1024, openai_api_key=openai.api_key))
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
    nodes = get_nodes_from_file(doc_file_path)
    index.insert_nodes(nodes, context=service_context)

    # 生成summary maxRecursion
    # index.summary = summary_index(index)
    index.summary = index.index_id
    index.storage_context.persist(persist_dir=os.path.join(index_save_directory, index.index_id))


def get_all_docs(index_):
    """
    通过index，获取所有文档
    :param index_:
    :return:
    """
    all_docs = index_.docstore.docs.values()
    # 创建一个空列表，用于存储节点 ID 和内容
    documents = []
    for doc in all_docs:
        node_id = doc.node_id
        doc_id = doc.ref_doc_id
        doc_text = doc.get_content()
        documents.append({"doc_id": doc_id, "node_id": node_id, "text": doc_text})
    return documents


def updateNodeById(index_, id_, text):
    """
    :param index_: 索引
    :param id_: node_id
    :param text: 更改后的内容
    :return:
    """
    node = index_.docstore.docs[id_]
    node.set_content(text)
    index_.docstore.add_documents([node])

def deleteNodeById(index_, id_,):
    """
    :param index_: 索引
    :param id_: node_id
    :return:
    """
    index_.docstore.delete_document(id_)


def deleteDocById(index, id):
    """
    # 删除文档
    :param id: 文档的id
    :return:
    """
    id = id.replace("\\\\", "\\")
    index.delete_ref_doc(id, delete_from_docstore=True)


def saveIndex(index):
    index.storage_context.persist(os.path.join(index_save_directory + index.index_id))


def compose_indices_to_graph() -> BaseChatEngine:
    """
    将index合成为graph
    :return: chat_engine
    """
    if indexes is None:
        loadAllIndexes()
    summaries = []
    for i in indexes:
        summaries.append(i.summary)
    graph = ComposableGraph.from_indices(
        ListIndex,
        indexes,
        index_summaries=summaries,
    )
    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=graph.as_query_engine(text_qa_template=Prompt(Prompts.QA_PROMPT), streaming=True),
        condense_question_prompt=Prompt(Prompts.CONDENSE_QUESTION_PROMPT),
        verbose=True,
        chat_mode="condense_question",
    )
    return chat_engine


def compose() -> BaseQueryEngine:
    """
        将index合成为graph
        :return: chat_engine
        """
    if indexes is None:
        loadAllIndexes()
    summaries = []
    for i in indexes:
        summaries.append(i.summary)
    graph = ComposableGraph.from_indices(
        ListIndex,
        indexes,
        index_summaries=summaries,
    )

    query_engine = graph.as_query_engine(streaming=True)
    return query_engine


def summary_index(index):
    """
         生成 summary
    """
    summary = index.as_query_engine(response_mode="tree_summarize").query(
        "文档描述"
    )
    # 去掉换行符、制表符、多余的空格和其他非字母数字字符
    summary_str = re.sub(r"\s+", " ", str(summary))
    summary_str = re.sub(r"[^\w\s]", "", summary_str)
    logging.info(f"Summary: {summary_str}")
    return summary_str


def query_index(index: BaseIndex, query_str):
    """
    查询文档获取响应
    :return: respoonse
    """
    ret = index.as_query_engine(text_qa_template=Prompt(Prompts.QA_PROMPT)).query(query_str)
    return ret


def get_history_msg(chat_engine: BaseChatEngine):
    """
    获取对话记录
    :param chat_engine:
    :return:
    """
    return chat_engine.chat_history


def get_index_by_name(index_name):
    index: VectorStoreIndex = None
    for i in indexes:
        if i.index_id == index_name:
            index = i
            break
    return index


def get_prompt_by_name(prompt_type):
    """获取Prompt"""
    return Prompt(getattr(Prompts, prompt_type.value))


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
        for key, value in node_data:
            if key == 'text':
                node_text = value
                # 去除空格和换行符
                node_text = node_text.strip().replace('\n', '').replace('\r', '')
                text_list.append(node_text)

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text_list))

def test(index):
    """将index转换为file"""
    data = index.docstore.docs
    print(data)
    text_list = []
    for node_id, node_data in data.items():
        for key, value in node_data:
            if key == 'text':
                node_text = value
                # 去除空格和换行符
                node_text = node_text.strip().replace('\n', '').replace('\r', '')
                text_list.append(node_text)



if __name__ == "__main__":
    loadAllIndexes()
    index=get_index_by_name('t2')
    test(index)

