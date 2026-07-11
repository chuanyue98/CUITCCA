import re
import logging

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
    indexes_snapshot: list | None = None,
) -> RouterQueryEngine:
    target_indexes = indexes_snapshot if indexes_snapshot is not None else indexes
    query_engine_tools = []
    for index in target_indexes:
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
        indexes_snapshot = list(indexes)

    query_engine = _build_router_query_engine(streaming=True, indexes_snapshot=indexes_snapshot)

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
