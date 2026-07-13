"""backend/app/handlers/qa_workflow.py 的测试（Phase 3）。

覆盖：
1. _build_retriever 的索引选择分支（0/1/多个索引），确认和
   graph_builder._build_query_engine 用的是同一套 top_k 常量 / selector。
2. QAWorkflow 的 step 事件流转：RetrieveEvent 正确携带检索到的 nodes，
   TokenEvent 在流式模式下逐个产出，最终 StopEvent.result 里的 response
   和 source_nodes 都正确。
3. 没检索到任何内容时的兜底文案。
4. max_retrieval_iterations 钩子：>1 时只记录一条日志，仍然只跑 1 轮检索。
5. chat_history 被正确带进发给 LLM 的消息列表。

全部用注入的 FakeRetriever / MockLLM（或能捕获调用参数的假 LLM），不碰真实
索引、不联网、不需要 API key。
"""
from unittest.mock import MagicMock, patch

import pytest
from handlers.qa_workflow import (
    RetrieveEvent,
    TokenEvent,
    _build_retriever,
    _EmptyRetriever,
)
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.llms import MockLLM
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from pydantic import PrivateAttr

import tests._pathsetup  # noqa: F401


def _make_node(text: str, file_name: str = "测试文档.txt", score: float = 0.9) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=text, metadata={"file_name": file_name}), score=score)


class FakeRetriever(BaseRetriever):
    """返回固定 nodes 的假 retriever，记录被调用了几次/传了什么 query。"""

    def __init__(self, nodes: list[NodeWithScore]):
        self._nodes = nodes
        self.calls: list[str] = []
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        self.calls.append(query_bundle.query_str)
        return self._nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self._retrieve(query_bundle)


class RecordingLLM(MockLLM):
    """继承 MockLLM 拿到能跑的流式/非流式实现，额外记录收到的 messages。

    MockLLM 是 pydantic BaseModel，不能像普通对象那样随手挂实例属性，记录
    列表要声明成 PrivateAttr。
    """

    _received_messages: list[list[ChatMessage]] = PrivateAttr(default_factory=list)

    @property
    def received_messages(self) -> list[list[ChatMessage]]:
        return self._received_messages

    async def achat(self, messages, **kwargs):
        self._received_messages.append(list(messages))
        return await super().achat(messages, **kwargs)

    async def astream_chat(self, messages, **kwargs):
        self._received_messages.append(list(messages))
        return await super().astream_chat(messages, **kwargs)


# ── _build_retriever: 索引选择分支 ──────────────────────────────────


def test_build_retriever_with_no_indexes_returns_empty_retriever():
    with patch("handlers.qa_workflow.indexes", []):
        retriever = _build_retriever()
    assert isinstance(retriever, _EmptyRetriever)


@pytest.mark.asyncio
async def test_empty_retriever_returns_no_nodes():
    retriever = _EmptyRetriever()
    nodes = await retriever.aretrieve(QueryBundle(query_str="随便问点什么"))
    assert nodes == []


def test_build_retriever_with_single_index_uses_its_retriever_with_shared_top_k():
    from configs.load_env import DEFAULT_SIMILARITY_TOP_K

    fake_index = MagicMock()
    fake_index.index_id = "idx1"
    fake_retriever = MagicMock()
    fake_index.as_retriever.return_value = fake_retriever

    with patch("handlers.qa_workflow.indexes", [fake_index]):
        retriever = _build_retriever()

    fake_index.as_retriever.assert_called_once_with(similarity_top_k=DEFAULT_SIMILARITY_TOP_K)
    assert retriever is fake_retriever


def test_build_retriever_with_multiple_indexes_uses_router_retriever():
    """多个索引应该走 RouterRetriever（RetrieverTool + 同一个 LLMSingleSelector），
    和 graph_builder._build_query_engine 的多索引分支用同一套选择器类，不是
    重新发明的路由逻辑。"""
    from llama_index.core import Settings
    from llama_index.core.retrievers import RouterRetriever

    fake_index1 = MagicMock()
    fake_index1.index_id = "idx1"
    fake_index1.summary = "campus dorm rules"
    fake_index1.as_retriever.return_value = MagicMock()

    fake_index2 = MagicMock()
    fake_index2.index_id = "idx2"
    fake_index2.summary = "campus dining hours"
    fake_index2.as_retriever.return_value = MagicMock()

    # LLMSingleSelector.from_defaults() 不传 llm 时会去解析 Settings.llm，
    # 未配置 API key 的环境里会报错——和 test_graph_router.py 里同样的原因，
    # 这里同样直接把 Settings._llm 打桩掉，只关心路由到了 RouterRetriever。
    with patch("handlers.qa_workflow.indexes", [fake_index1, fake_index2]), \
            patch.object(Settings, "_llm", MagicMock()):
        retriever = _build_retriever()

    assert isinstance(retriever, RouterRetriever)


# ── QAWorkflow: 事件流转 / 流式 / 兜底文案 ──────────────────────────


@pytest.mark.asyncio
async def test_workflow_nonstreaming_returns_response_and_source_nodes():
    from handlers.qa_workflow import QAWorkflow

    nodes = [_make_node("校训是成于大气 信达天下", file_name="大学精神.txt")]
    retriever = FakeRetriever(nodes)
    llm = RecordingLLM()

    workflow = QAWorkflow(retriever=retriever, llm=llm, timeout=30)
    result = await workflow.run(query="学校的校训是什么？", streaming=False)

    assert result.source_nodes == nodes
    assert result.response.strip() != ""
    assert retriever.calls == ["学校的校训是什么？"]


@pytest.mark.asyncio
async def test_workflow_streaming_emits_token_events_and_matches_final_result():
    from handlers.qa_workflow import QAWorkflow

    nodes = [_make_node("校训是成于大气 信达天下", file_name="大学精神.txt")]
    workflow = QAWorkflow(retriever=FakeRetriever(nodes), llm=RecordingLLM(), timeout=30)

    handler = workflow.run(query="学校的校训是什么？", streaming=True)
    tokens: list[str] = []
    async for ev in handler.stream_events():
        if isinstance(ev, TokenEvent):
            tokens.append(ev.token)

    result = await handler

    assert tokens, "流式模式应该至少产出一个 TokenEvent"
    assert "".join(tokens) == result.response


@pytest.mark.asyncio
async def test_workflow_falls_back_when_no_nodes_retrieved():
    from handlers.qa_workflow import _FALLBACK_ANSWER, QAWorkflow

    workflow = QAWorkflow(retriever=FakeRetriever([]), llm=RecordingLLM(), timeout=30)
    result = await workflow.run(query="随便问点什么", streaming=False)

    assert result.response == _FALLBACK_ANSWER
    assert result.source_nodes == []


@pytest.mark.asyncio
async def test_workflow_falls_back_streaming_when_no_nodes_retrieved():
    from handlers.qa_workflow import _FALLBACK_ANSWER, QAWorkflow

    workflow = QAWorkflow(retriever=FakeRetriever([]), llm=RecordingLLM(), timeout=30)
    handler = workflow.run(query="随便问点什么", streaming=True)

    tokens = [ev.token async for ev in handler.stream_events() if isinstance(ev, TokenEvent)]
    result = await handler

    assert tokens == [_FALLBACK_ANSWER]
    assert result.response == _FALLBACK_ANSWER


@pytest.mark.asyncio
async def test_max_retrieval_iterations_hook_still_runs_exactly_once():
    """>1 目前只是记录日志，钩子占位，不假装支持多轮检索。"""
    from handlers.qa_workflow import QAWorkflow

    nodes = [_make_node("一些内容")]
    retriever = FakeRetriever(nodes)
    workflow = QAWorkflow(retriever=retriever, llm=RecordingLLM(), max_retrieval_iterations=3, timeout=30)

    await workflow.run(query="问题", streaming=False)

    assert len(retriever.calls) == 1, "当前版本 max_retrieval_iterations>1 不应该真的多跑几轮检索"


@pytest.mark.asyncio
async def test_chat_history_is_forwarded_to_llm():
    from handlers.qa_workflow import QAWorkflow

    nodes = [_make_node("一些内容")]
    llm = RecordingLLM()
    workflow = QAWorkflow(retriever=FakeRetriever(nodes), llm=llm, timeout=30)

    history = [ChatMessage(role=MessageRole.USER, content="之前问过的问题")]
    await workflow.run(query="追问", chat_history=history, streaming=False)

    assert llm.received_messages, "LLM 应该被调用过一次"
    sent_messages = llm.received_messages[0]
    assert sent_messages[0].content == "之前问过的问题"
    assert sent_messages[-1].role == MessageRole.USER


@pytest.mark.asyncio
async def test_retrieve_event_carries_nodes_and_query():
    """直接测 RetrieveEvent 本身携带的数据结构，不经过完整 workflow 跑一遍。"""
    nodes = [_make_node("内容 A"), _make_node("内容 B")]
    ev = RetrieveEvent(nodes=nodes, query_str="问题", chat_history=[], streaming=True)

    assert ev.nodes == nodes
    assert ev.query_str == "问题"
    assert ev.streaming is True
