import asyncio
import re

from configs.config import Prompts
from llama_index.core import Settings, SimpleDirectoryReader
from llama_index.core.indices.base import BaseIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.tools import QueryEngineTool

_DEFAULT_QA_INSTRUCTION = (
    "请根据以下内容生成尽可能多的问答对。\n"
    "要求：问题和答案都需完整详细。\n"
    "按下面格式返回：\n"
    "Q:\nA:\nQ:\nA:\n..."
)


def build_qa_generation_prompt(custom_prompt: str | None) -> str:
    """
    构造用于 QA 生成的指令。只返回指令本身，不拼接文档内容——
    文档内容由 generate_qa_batched 按 chunk 拼接，这里重复拼入整篇内容
    会导致每个 chunk 请求都携带一份完整文档，浪费大量 token。
    """
    return custom_prompt or _DEFAULT_QA_INSTRUCTION


def get_nodes_from_file(file_path):
    """
    从文件中获取节点
    :param file_path: 文件路径
    :return:
    """
    splitter = SentenceSplitter.from_defaults()
    documents = SimpleDirectoryReader(input_files=[file_path], filename_as_id=True).load_data()
    for doc in documents:
        doc.id_ = extract_content_after_backslash(doc.id_)
    return splitter.get_nodes_from_documents(documents)


def extract_content_after_backslash(string: str) -> str:
    """
    去除文件名中的路径（同时兼容 Windows 反斜杠路径和 POSIX 正斜杠路径）
    :param string:
    :return:
    """
    return string.replace('\\', '/').rsplit('/', 1)[-1]


def formatted_pairs(qa_data_list):
    """
    格式化问答对
    :param qa_data_list: 问答数据列表
    :return: 提取出的问答对列表
    """
    qa_pairs = []
    pattern = r'(?:Q: |A: )'
    for qa_data in qa_data_list:
        pairs = re.split(pattern, qa_data)
        pairs = [pair.strip() for pair in pairs if pair.strip()]
        qa_pairs.extend(pairs)
    return qa_pairs


async def generate_qa_batched(contents: str, prompt: str | None = None):
    """
    生成QA对
    :param contents:
    :return:
    """
    contents = contents.replace("\n", "")
    contents = contents.strip()
    textSplitter = SentenceSplitter(chunk_size=1024)
    chunks: list[str] = textSplitter.split_text(contents)
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
    tasks = [sem_complete(content) for content in chunks]
    responses = await asyncio.gather(*tasks)
    qa_pairs = [res.text for res in responses if res]

    return qa_pairs


def index_description(index: BaseIndex) -> str:
    """索引的人类可读描述，供 selector（RouterQueryEngine/RouterRetriever）挑选
    索引时展示。用 ``.summary``（如果已经设置过），否则退化成 index_id。

    被 ``generate_query_engine_tools()``（下面）和
    ``handlers/qa_workflow.py`` 的 ``_build_retriever()`` 多索引分支共用——
    两边过去各自内联同一行表达式，抽出来避免两处失步。
    """
    return getattr(index, "summary", None) or f"知识库索引: {index.index_id}"


def generate_query_engine_tools(
    indexes: list[BaseIndex], streaming: bool = False, similarity_top_k: int = 5
) -> list[QueryEngineTool]:
    query_engine_tools = []
    for index in indexes:
        query_engine = index.as_query_engine(
            streaming=streaming,
            text_qa_template=Prompts.QA_PROMPT.value,
            refine_template=Prompts.REFINE_PROMPT.value,
            similarity_top_k=similarity_top_k,
        )
        tool = QueryEngineTool.from_defaults(query_engine=query_engine, description=index_description(index))
        query_engine_tools.append(tool)

    return query_engine_tools


if __name__ == '__main__':
    _test_urls = (
        "本科招生http://zjc.cuit.edu.cn/Index.htm"
        "研究生招生https://yjsc.cuit.edu.cn/"
        "继续教育招生https://cjy.cuit.edu.cn/"
    )
    res = asyncio.run(generate_qa_batched(_test_urls))
    print(res)
