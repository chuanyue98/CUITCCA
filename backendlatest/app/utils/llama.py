import json
import re
from typing import List, Any

from langchain.text_splitter import SpacyTextSplitter
from llama_index import SimpleDirectoryReader
from llama_index.indices.base import BaseIndex
from llama_index.llms import ChatMessage, OpenAI
from llama_index.node_parser import SimpleNodeParser
from llama_index.tools import QueryEngineTool

from configs.config import Prompts
from utils.logger import customer_logger


def get_nodes_from_file(file_path):
    """
    从文件中获取节点
    :param file_path: 文件路径
    :return:
    """
    # 加载文本分词器

    text_splitter = SpacyTextSplitter(pipeline="zh_core_web_sm", chunk_size=512)
    parser = SimpleNodeParser.from_defaults(text_splitter=text_splitter)
    documents = SimpleDirectoryReader(file_path, filename_as_id=True).load_data()
    for doc in documents:
        doc.id_ = extract_content_after_backslash(doc.id_)
    return parser.get_nodes_from_documents(documents)


def extract_content_after_backslash(string):
    """
    去除文件名中的路径
    :param string:
    :return:
    """
    parts = string.split('\\')
    return parts[-1]


def formatted_pairs(qa_data_list):
    """将字符串中的QA对格式化，返回列表"""
    qa_pairs = []
    pattern = r'(?:Q: |A: )'
    for qa_data in qa_data_list:
        pairs = re.split(pattern, qa_data)
        pairs = [pair.strip() for pair in pairs if pair.strip()]
        qa_pairs.extend(pairs)
    return qa_pairs


async def generate_qa_batched(contents: str, prompt: str = None):
    """
    生成QA对
    :param contents:
    :return:
    """
    contents = contents.replace("\n", "")
    contents = contents.strip()
    textSplitter = SpacyTextSplitter(pipeline="zh_core_web_sm", chunk_size=1024)
    contents = textSplitter.split_text(contents)
    if prompt is None:
        prompt = "我会发送一段长文本"
    messages = [
        ChatMessage(role="system", content=f"""你是出题人。
{prompt}从中提取出 25 个问题和答案。 问题答案详完整详细,按下面格式返回:
Q:
A:
Q:
A:
...""")
    ]

    qa_pairs = []
    for content in contents:
        messages.append(ChatMessage(role="user", content=content))
        response = await OpenAI().achat(messages)
        if response.message:
            assistant_message = response.message.content
            customer_logger.info(f"{assistant_message}")
            qa_pairs.append(assistant_message)
        messages = messages[:1]

    return qa_pairs


def generate_query_engine_tools(indexes: List[BaseIndex]) -> List[QueryEngineTool]:
    query_engine_tools = []
    for index in indexes:
        query_engine = index.as_query_engine(streaming=True,
                                             text_qa_template=Prompts.QA_PROMPT.value,
                                             refine_template=Prompts.REFINE_PROMPT.value)
        description = index.summary
        tool = QueryEngineTool.from_defaults(query_engine=query_engine, description=description)
        query_engine_tools.append(tool)

    return query_engine_tools


def remove_vector_store(path, doc_id):
    with open(path, 'r') as file:
        data = json.load(file)

    embedding_dict = data['embedding_dict']
    text_id_to_ref_doc_id = data['text_id_to_ref_doc_id']

    # 删除embedding_dict中的内容
    if doc_id in embedding_dict:
        del embedding_dict[doc_id]

    # 删除text_id_to_ref_doc_id字典中的对应项
    if doc_id in text_id_to_ref_doc_id:
        del text_id_to_ref_doc_id[doc_id]

    with open(path, 'w') as file:
        json.dump(data, file, indent=4)


def remove_index_store(path, doc_id):
    with open(path, 'r') as file:
        data = json.load(file)

    if "index_store/data" in data:
        index_data = data["index_store/data"]
        for key, value in index_data.items():
            if "__data__" in value:
                data_str = value["__data__"]
                data_dict = json.loads(data_str)
                if "nodes_dict" in data_dict and doc_id in data_dict["nodes_dict"]:
                    del data_dict["nodes_dict"][doc_id]
                    value["__data__"] = json.dumps(data_dict)
                    break

    with open(path, 'w') as file:
        json.dump(data, file, indent=4)


def remove_docstore(path, doc_id):
    # 读取JSON文件
    with open(path, 'r') as file:
        data = json.load(file)

    # 检查是否存在指定的doc_id
    if doc_id in data['docstore/data']:
        # 删除指定的doc_id信息
        del data['docstore/data'][doc_id]

        # 删除相关的ref_doc_info和metadata
        if doc_id in data['docstore/ref_doc_info']:
            del data['docstore/ref_doc_info'][doc_id]

        if doc_id in data['docstore/metadata']:
            del data['docstore/metadata'][doc_id]

    # 写回JSON文件
    with open(path, 'w') as file:
        json.dump(data, file, indent=4)


if __name__ == '__main__':
    nodes = get_nodes_from_file('../utils')
