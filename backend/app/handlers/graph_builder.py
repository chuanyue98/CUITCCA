import re
import logging

from llama_index.core import ComposableGraph, VectorStoreIndex, get_response_synthesizer
from llama_index.core.chat_engine import CondenseQuestionChatEngine
from llama_index.core.chat_engine.types import BaseChatEngine
from llama_index.core.indices.query.base import BaseQueryEngine

from configs.config import Prompts
from configs.load_env import VERBOSE
from handlers.index_crud import indexes, _indexes_lock


async def compose_graph_chat_egine() -> BaseChatEngine:
    """
    将index合成为graph
    :return: chat_engine
    """
    async with _indexes_lock:
        summaries = [i.summary for i in indexes]
        _indexes_snapshot = list(indexes)

    graph = ComposableGraph.from_indices(
        VectorStoreIndex,
        _indexes_snapshot,
        index_summaries=summaries,
    )
    custom_query_engines = {
        index.index_id: index.as_query_engine(
            child_branch_factor=2
        )
        for index in _indexes_snapshot
    }

    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=graph.as_query_engine(text_qa_template=Prompts.QA_PROMPT.value,
                                           refine_template=Prompts.REFINE_PROMPT.value,
                                           streaming=True,
                                           similarity_top_k=3,
                                           verbose=VERBOSE,
                                           custom_query_engines=custom_query_engines,),
        condense_question_prompt=Prompts.CONDENSE_QUESTION_PROMPT.value,
        verbose=VERBOSE,
        chat_mode="condense_question",
    )

    return chat_engine


def compose_graph_query_engine(streaming=False) -> BaseQueryEngine:
    """
    将index合成为graph
    :return: query_engine
    """
    summaries = []
    for i in indexes:
        summaries.append(i.summary)
    graph = ComposableGraph.from_indices(
        VectorStoreIndex,
        indexes,
        index_summaries=summaries,
    )
    custom_query_engines = {
        index.index_id: index.as_query_engine(
            child_branch_factor=3
        )
        for index in indexes
    }
    response_synthesizer = get_response_synthesizer(structured_answer_filtering=True)

    query_engine = graph.as_query_engine(text_qa_template=Prompts.QA_PROMPT.value,
                                         refine_template=Prompts.REFINE_PROMPT.value,
                                         streaming=streaming,
                                         similarity_top_k=3,
                                         verbose=VERBOSE,
                                         )
    return query_engine


async def summary_index(index):
    """
         生成 summary
    """
    summary = await index.as_query_engine(response_mode="tree_summarize").aquery(
        "总结，生成文章摘要，要覆盖所有要点，方便后续检索,不需要详细内容，只需要关键信息，方便后续检索")
    # 去掉换行符、制表符、多余的空格和其他非字母数字字符
    summary_str = re.sub(r"\s+", " ", str(summary))
    summary_str = re.sub(r"[^\w\s]", "", summary_str)
    logging.info(f"Summary: {summary_str}")
    return summary_str


def get_history_msg(chat_engine: BaseChatEngine):
    """
    获取对话记录
    :param chat_engine:
    :return:
    """
    return chat_engine.chat_history
