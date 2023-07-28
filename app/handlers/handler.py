import os
import re
from dotenv import load_dotenv
import logging

import openai
from langchain.chat_models import ChatOpenAI
from langchain.text_splitter import SpacyTextSplitter
from llama_index import VectorStoreIndex, Document, load_index_from_storage, StorageContext, ServiceContext, \
    SimpleDirectoryReader, LLMPredictor, ComposableGraph, ListIndex, Prompt
from llama_index.chat_engine import CondenseQuestionChatEngine
from llama_index.chat_engine.types import BaseChatEngine
from llama_index.llms import OpenAI
from llama_index.node_parser import SimpleNodeParser


load_dotenv()
openai.api_key = os.environ.get("OPENAI_API_KEY")
openai.api_base = os.environ.get('OPENAI_API_BASE')
index_save_directory = os.environ.get('INDEX_SAVE_DIRECTORY')
SAVE_PATH = os.environ.get('SAVE_PATH')
LOAD_PATH = os.environ.get('LOAD_PATH')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
indexes = []

QA_PROMPT_TMPL = ("下面是有关内容\n" "---------------------\n"
                  "{context_str}" "\n---------------------\n"
                  "根据这些信息，请回答问题: {query_str}\n"
                  "如果问题中提到图片，回答的内容有url,请使用markdown格式输出图片"
                  "如果您不知道的话，请回答不知道\n")

QA_PROMPT_TMPL = Prompt(QA_PROMPT_TMPL)


def createIndexZh(index_name):
    global index
    llm_predictor = LLMPredictor(
        llm=ChatOpenAI(temperature=0.1, model_name="gpt-3.5-turbo-16k", max_tokens=1024, openai_api_key=openai.api_key))
    text_splitter = SpacyTextSplitter(pipeline="zh_core_web_sm", chunk_size=512)
    parser = SimpleNodeParser(text_splitter=text_splitter)
    documents = SimpleDirectoryReader('./data', filename_as_id=True).load_data()
    nodes = parser.get_nodes_from_documents(documents)
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
    index = VectorStoreIndex(nodes, service_context=service_context)
    index.storage_context.persist(index_save_directory + index_name)


def createIndex(index_name):
    """
    创建索引
    :param index_name: 索引名称
    :return:
    """
    index = VectorStoreIndex([])
    index.set_index_id(index_name)
    logging.info(f"index保存位置: {index_save_directory + index_name}")
    index.storage_context.persist(index_save_directory + index_name)


def loadAllIndexes(index_save_directory):
    """
    加载索引数据
    :param index_save_directory: 索引保存目录
    :return:
    """
    index_save_directory = os.path.join(PROJECT_ROOT,index_save_directory)
    for index_dir_name in get_subfolders_list(index_save_directory):
        # 获取索引目录的完整路径
        index_dir_path = os.path.join(index_save_directory, index_dir_name)
        storage_context = StorageContext.from_defaults(persist_dir=index_dir_path)
        index = load_index_from_storage(storage_context)
        indexes.append(index)


def insert_doc(index, text, id=None):
    doc = Document(text=text, doc_id=id)
    index.insert(doc)


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
    text_splitter = SpacyTextSplitter(pipeline="zh_core_web_sm", chunk_size=512)
    parser = SimpleNodeParser(text_splitter=text_splitter)
    documents = SimpleDirectoryReader(doc_file_path, filename_as_id=True).load_data()
    nodes = parser.get_nodes_from_documents(documents)
    service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
    index.insert_nodes(nodes, context=service_context)

    # 生成summary maxRecursion
    # index.summary = summary_index(index)
    index.summary = index.index_id
    index.storage_context.persist(persist_dir=os.path.join(PROJECT_ROOT,index_save_directory,index.index_id))


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


def get_doc_by_id(index, doc_id):
    """
    通过node_id获取所在的Doc
    :param doc_id: 文档id
    :param index: 索引
    :return: 文档列表
    """
    return [doc for doc in get_all_docs(index) if doc['doc_id'] == doc_id]


def updateNodeById(index, id, text):
    node = index.docstore.get_node(node_id=id)
    node.set_content(text)
    doc = Document(doc_id=node.ref_doc_id, text=node.get_content())
    index.update_ref_doc(doc, update_kwargs={"delete_kwargs": {'delete_from_docstore': True}})


# 更新node
def updateById(index_, id_, text):
    """
    通过node_id，更新node中的内容 会删除doc中所有node再重新添加，node_id会变化
    :param index_: 索引
    :param id_: node_id
    :param text: 更改后的内容
    :return:
    """
    node = index_.docstore.get_node(node_id=id_)
    doc_id = node.ref_doc_id
    docs = get_doc_by_id(index_, doc_id)
    documents = [Document(id_=doc_id, text=text if node['node_id'] == id_ else node['text']) for node in docs]
    deleteDocById(index_, doc_id)
    for doc in documents:
        index_.insert(doc)


def deleteDocById(index, id):
    """
    # 删除文档
    :param id: 文档的id
    :return:
    """
    id = id.replace("\\\\", "\\")
    print(f"updating id {id}")
    index.delete_ref_doc(id, delete_from_docstore=True)


def saveIndex(index):
    index.storage_context.persist(index_save_directory + index.index_id)


def printnodes(index):
    for doc in get_all_docs(index):
        print(doc, end="\n")
    print("---------")


def compose_indices_to_graph():
    """
    将index合成为graph
    :return: graph
    """
    if indexes is None:
        loadAllIndexes(index_save_directory)
    summaries = []
    storage_contexts = []
    llm = OpenAI(temperature=0,max_tokens=512)
    for i in indexes:
        summaries.append(i.summary)
    graph = ComposableGraph.from_indices(
        ListIndex,
        indexes,
        index_summaries=summaries,
    )
    custom_prompt = Prompt("""\
    给定一段人类用户与AI助手之间的对话历史和人类用户的后续留言, \
    将消息改写成一个独立问题，以捕捉对话中的所有相关上下文。\

    <Chat History> 
    {chat_history}
    
    <Follow Up Message>
    {question}

    <Standalone question>
    """)
    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=graph.as_query_engine(),
        condense_question_prompt=custom_prompt,
        text_qa_template=QA_PROMPT_TMPL,
        verbose=True
    )
    return chat_engine


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


def query_index(index, query_str):
    """
    查询文档获取响应
    :return: respoonse
    """
    ret = index.as_query_engine(text_qa_template=QA_PROMPT_TMPL).query(query_str)
    return ret


def get_subfolders_list(root_dir: str) -> list:
    """
    遍历指定目录下的所有子目录，并将子目录名称存储在一个列表中返回。
    """
    subfolders_list = []
    dir = os.path.join(PROJECT_ROOT,root_dir)
    for dirpath, dirnames, filenames in os.walk(dir):
        for dirname in dirnames:
            subfolders_list.append(dirname)
    return subfolders_list

def get_history_msg(chat_engine:BaseChatEngine):
    """
    获取对话记录
    :param chat_engine:
    :return:
    """
    return chat_engine.chat_history


if __name__ == "__main__":
    loadAllIndexes(index_save_directory)
    print(indexes)