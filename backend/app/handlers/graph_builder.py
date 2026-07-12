import asyncio
import logging
import re

from configs.config import Prompts
from configs.load_env import VERBOSE
from handlers.index_crud import indexes
from llama_index.core.base.response.schema import RESPONSE_TYPE
from llama_index.core.callbacks import CallbackManager
from llama_index.core.chat_engine import CondenseQuestionChatEngine
from llama_index.core.chat_engine.types import BaseChatEngine
from llama_index.core.indices.query.base import BaseQueryEngine
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.selectors import LLMSingleSelector
from utils.llama import generate_query_engine_tools


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
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self._aquery(query))
        except RuntimeError:
            pass
        return asyncio.run(self._aquery(query))

    def _get_prompt_modules(self):
        return []


_query_engine_caches: dict[bool, BaseQueryEngine] = {}


def _build_query_engine(streaming: bool) -> BaseQueryEngine:
    indexes_snapshot = list(indexes)
    if not indexes_snapshot:
        return MultiIndexQueryEngine(indexes_snapshot=[], streaming=streaming)
    if len(indexes_snapshot) == 1:
        # 单索引无需路由选择，直接查询避免额外的 LLM 选择调用
        return indexes_snapshot[0].as_query_engine(
            streaming=streaming,
            text_qa_template=Prompts.QA_PROMPT.value,
            refine_template=Prompts.REFINE_PROMPT.value,
            similarity_top_k=5,
        )
    tools = generate_query_engine_tools(indexes_snapshot, streaming=streaming, similarity_top_k=5)
    return RouterQueryEngine.from_defaults(
        query_engine_tools=tools,
        selector=LLMSingleSelector.from_defaults(),
        # select_multi=False：每次查询只选一个最相关的索引，而不是跨索引汇总。
        # select_multi=True 会为每次查询多花一次 LLM 摘要调用，使延迟翻倍，
        # 这对于按院系/主题分区的校园问答场景通常不划算——一个问题很少同时
        # 横跨多个知识库。如果未来发现跨主题查询很常见，可以重新评估这个取舍。
        select_multi=False,
        verbose=VERBOSE,
    )


def compose_graph_chat_egine() -> BaseChatEngine:
    query_engine = _build_query_engine(streaming=True)

    chat_engine = CondenseQuestionChatEngine.from_defaults(
        query_engine=query_engine,
        condense_question_prompt=Prompts.CONDENSE_QUESTION_PROMPT.value,
        verbose=VERBOSE,
    )

    return chat_engine


def compose_graph_query_engine(streaming: bool = False) -> BaseQueryEngine:
    # 按 streaming 值分别缓存：之前是单槽缓存，谁先调用就把该 streaming 值
    # 永久固定下来，后续用另一个 streaming 值调用的调用方会静默拿到错误类型的
    # engine（例如 /query_stream 会拿到不支持 response_gen 的非流式 Response）。
    if streaming not in _query_engine_caches:
        _query_engine_caches[streaming] = _build_query_engine(streaming)
    return _query_engine_caches[streaming]


def invalidate_query_engine_cache():
    _query_engine_caches.clear()


async def summary_index(index):
    summary = await index.as_query_engine(response_mode="tree_summarize").aquery(
        "总结，生成文章摘要，要覆盖所有要点，方便后续检索,不需要详细内容，只需要关键信息，方便后续检索")
    summary_str = re.sub(r"\s+", " ", str(summary))
    summary_str = re.sub(r"[^\w\s]", "", summary_str)
    logging.info(f"Summary: {summary_str}")
    return summary_str


def get_history_msg(chat_engine: BaseChatEngine):
    return chat_engine.chat_history
