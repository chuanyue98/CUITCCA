import logging
import re

from configs.config import Prompts
from configs.load_env import VERBOSE
from handlers.index_crud import _indexes_lock, indexes
from llama_index.core.base.response.schema import RESPONSE_TYPE
from llama_index.core.callbacks import CallbackManager
from llama_index.core.chat_engine import CondenseQuestionChatEngine
from llama_index.core.chat_engine.types import BaseChatEngine
from llama_index.core.indices.query.base import BaseQueryEngine


class MultiIndexQueryEngine(BaseQueryEngine):
    """Queries all indexes and returns the first non-empty response."""

    def __init__(self, indexes_snapshot: list, streaming: bool = False):
        self._indexes_snapshot = indexes_snapshot
        self._streaming = streaming
        super().__init__(callback_manager=CallbackManager())

    def _get_query_engines(self):
        return [
            index.as_query_engine(
                streaming=self._streaming,
                text_qa_template=Prompts.QA_PROMPT.value,
                refine_template=Prompts.REFINE_PROMPT.value,
                similarity_top_k=3,
                verbose=VERBOSE,
            )
            for index in self._indexes_snapshot
        ]

    async def _aquery(self, query: str) -> RESPONSE_TYPE:  # type: ignore[override]
        for engine in self._get_query_engines():
            try:
                response = await engine.aquery(query)
                if str(response) and str(response) != "Empty Response":
                    return response
            except Exception:
                continue
        from llama_index.core.response import Response
        return Response("Empty Response")

    def _query(self, query: str) -> RESPONSE_TYPE:  # type: ignore[override]
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
        except RuntimeError:
            pass
        return asyncio.run(self._aquery(query))

    def _get_prompt_modules(self):
        return []


# Query engine 缓存
_query_engine_cache: MultiIndexQueryEngine | None = None
_query_engine_lock = None


def _get_query_engine_lock():
    global _query_engine_lock
    if _query_engine_lock is None:
        import asyncio
        _query_engine_lock = asyncio.Lock()
    return _query_engine_lock


def _build_multi_query_engine(
    streaming: bool = False,
    indexes_snapshot: list | None = None,
) -> MultiIndexQueryEngine:
    if indexes_snapshot is None:
        indexes_snapshot = list(indexes)
    return MultiIndexQueryEngine(indexes_snapshot=indexes_snapshot, streaming=streaming)


async def compose_graph_chat_egine() -> BaseChatEngine:
    async with _indexes_lock:
        indexes_snapshot = list(indexes)

    query_engine = _build_multi_query_engine(streaming=True, indexes_snapshot=indexes_snapshot)

    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=query_engine,
        condense_question_prompt=Prompts.CONDENSE_QUESTION_PROMPT.value,
        verbose=VERBOSE,
    )

    return chat_engine


def compose_graph_query_engine(streaming: bool = False) -> BaseQueryEngine:
    """获取查询引擎，使用缓存避免每次请求重建"""
    global _query_engine_cache
    if _query_engine_cache is None:
        _query_engine_cache = _build_multi_query_engine(streaming=streaming)
    return _query_engine_cache


def invalidate_query_engine_cache():
    """索引变更时调用，清除缓存"""
    global _query_engine_cache
    _query_engine_cache = None


async def summary_index(index):
    summary = await index.as_query_engine(response_mode="tree_summarize").aquery(
        "总结，生成文章摘要，要覆盖所有要点，方便后续检索,不需要详细内容，只需要关键信息，方便后续检索")
    summary_str = re.sub(r"\s+", " ", str(summary))
    summary_str = re.sub(r"[^\w\s]", "", summary_str)
    logging.info(f"Summary: {summary_str}")
    return summary_str


def get_history_msg(chat_engine: BaseChatEngine):
    return chat_engine.chat_history
