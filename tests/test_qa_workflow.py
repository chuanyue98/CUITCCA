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
6. condense_question step：chat_history 为空时零 LLM 调用、直接透传原始
   query；非空时压缩 LLM 被调用一次且 prompt 里带上了 chat_history/原始
   question，压缩结果同时驱动 retrieve 和 synthesize 两个 step；压缩 LLM
   报错时降级用原始 query，整个 workflow 不中断。

全部用注入的 FakeRetriever / MockLLM（或能捕获调用参数的假 LLM），不碰真实
索引、不联网、不需要 API key。
"""
from unittest.mock import MagicMock, patch

import pytest
from handlers.qa_workflow import (
    CondenseEvent,
    RetrieveEvent,
    TokenEvent,
    _build_retriever,
    _EmptyRetriever,
)
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.llms.types import ChatMessage, CompletionResponse, MessageRole
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
    """继承 MockLLM 拿到能跑的流式/非流式实现，额外记录收到的 messages/prompt。

    MockLLM 是 pydantic BaseModel，不能像普通对象那样随手挂实例属性，记录
    列表要声明成 PrivateAttr。``acomplete`` 是 condense_question step 用来
    压缩问题的调用；``set_condense_response``/``set_condense_error`` 让测试
    控制压缩结果或模拟压缩失败，不设置时退回 MockLLM 默认行为（原样回显
    prompt）。
    """

    _received_messages: list[list[ChatMessage]] = PrivateAttr(default_factory=list)
    _received_prompts: list[str] = PrivateAttr(default_factory=list)
    _condense_response: str | None = PrivateAttr(default=None)
    _condense_error: Exception | None = PrivateAttr(default=None)

    @property
    def received_messages(self) -> list[list[ChatMessage]]:
        return self._received_messages

    @property
    def received_prompts(self) -> list[str]:
        return self._received_prompts

    def set_condense_response(self, text: str) -> None:
        self._condense_response = text

    def set_condense_error(self, exc: Exception) -> None:
        self._condense_error = exc

    async def achat(self, messages, **kwargs):
        self._received_messages.append(list(messages))
        return await super().achat(messages, **kwargs)

    async def astream_chat(self, messages, **kwargs):
        self._received_messages.append(list(messages))
        return await super().astream_chat(messages, **kwargs)

    async def acomplete(self, prompt, **kwargs):
        self._received_prompts.append(prompt)
        if self._condense_error is not None:
            raise self._condense_error
        if self._condense_response is not None:
            return CompletionResponse(text=self._condense_response)
        return await super().acomplete(prompt, **kwargs)


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


def test_build_retriever_with_explicit_top_k_overrides_default():
    """Fix #6 回归测试：_build_retriever(top_k=...) 传参时应该用传入的值，
    而不是永远读 load_env.DEFAULT_SIMILARITY_TOP_K（否则
    evals/run_workflow_retrieval_eval.py 的 --top-k 就是个死参数）。"""
    fake_index = MagicMock()
    fake_index.index_id = "idx1"
    fake_retriever = MagicMock()
    fake_index.as_retriever.return_value = fake_retriever

    with patch("handlers.qa_workflow.indexes", [fake_index]):
        retriever = _build_retriever(top_k=3)

    fake_index.as_retriever.assert_called_once_with(similarity_top_k=3)
    assert retriever is fake_retriever


def test_build_retriever_without_top_k_still_uses_default():
    from configs.load_env import DEFAULT_SIMILARITY_TOP_K

    fake_index = MagicMock()
    fake_index.index_id = "idx1"
    fake_index.as_retriever.return_value = MagicMock()

    with patch("handlers.qa_workflow.indexes", [fake_index]):
        _build_retriever()

    fake_index.as_retriever.assert_called_once_with(similarity_top_k=DEFAULT_SIMILARITY_TOP_K)


def test_build_retriever_multi_index_and_generate_query_engine_tools_agree_on_description():
    """Fix #7 回归测试：qa_workflow._build_retriever() 的多索引分支和
    utils.llama.generate_query_engine_tools() 过去各自内联同一行
    `getattr(index, "summary", None) or f"知识库索引: {index.index_id}"`。
    现在都调用共享的 utils.llama.index_description()，对同一批索引应该产出
    完全相同的 description 字符串（覆盖有 summary 和没有 summary 两种情况）。
    """
    import utils.llama as llama_utils
    from llama_index.core import Settings
    from llama_index.core.tools import RetrieverTool

    class BareIndex:
        """没有 .summary 属性，走 fallback 分支——MagicMock 会自动生成
        .summary 属性掩盖这条分支，所以用一个朴素对象。"""

        def __init__(self, index_id: str):
            self.index_id = index_id
            self.vector_store = MagicMock()

        def as_query_engine(self, **kwargs):
            return MagicMock()

        def as_retriever(self, **kwargs):
            return MagicMock()

    index_with_summary = MagicMock()
    index_with_summary.index_id = "idx1"
    index_with_summary.summary = "campus dorm rules"
    index_with_summary.as_query_engine.return_value = MagicMock()
    index_with_summary.as_retriever.return_value = MagicMock()

    index_without_summary = BareIndex("idx2")
    indexes_list = [index_with_summary, index_without_summary]

    with patch("utils.llama.QueryEngineTool") as mock_tool_cls:
        llama_utils.generate_query_engine_tools(indexes_list)
    tool_descriptions = [call.kwargs["description"] for call in mock_tool_cls.from_defaults.call_args_list]

    captured_retriever_descriptions: list[str] = []
    real_from_defaults = RetrieverTool.from_defaults

    def _capture(*args, **kwargs):
        captured_retriever_descriptions.append(kwargs["description"])
        return real_from_defaults(*args, **kwargs)

    with patch("handlers.qa_workflow.indexes", indexes_list), \
            patch.object(Settings, "_llm", MagicMock()), \
            patch("handlers.qa_workflow.RetrieverTool.from_defaults", side_effect=_capture):
        _build_retriever()

    assert tool_descriptions == captured_retriever_descriptions == ["campus dorm rules", "知识库索引: idx2"]


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


# ── condense_question step：多轮追问压缩 ────────────────────────────


@pytest.mark.asyncio
async def test_condense_question_skipped_when_chat_history_empty():
    """chat_history 为空（含不传）时不应该触发任何压缩 LLM 调用，检索用的
    还是原始 query——单轮问答主路径零额外开销。"""
    from handlers.qa_workflow import QAWorkflow

    nodes = [_make_node("一些内容")]
    retriever = FakeRetriever(nodes)
    llm = RecordingLLM()
    workflow = QAWorkflow(retriever=retriever, llm=llm, timeout=30)

    result = await workflow.run(query="学校的校训是什么？", streaming=False)

    assert retriever.calls == ["学校的校训是什么？"]
    assert llm.received_prompts == [], "chat_history 为空时压缩用的 acomplete 不应该被调用"
    assert result.response.strip() != ""


@pytest.mark.asyncio
async def test_condense_question_used_when_chat_history_present():
    """chat_history 非空：压缩 LLM 被调用一次，prompt 里带上了 chat_history
    和原始 question；retrieve 和 synthesize 两个 step 用的都是压缩后的问题，
    不是原始 query。"""
    from handlers.qa_workflow import QAWorkflow

    nodes = [_make_node("一些内容")]
    retriever = FakeRetriever(nodes)
    llm = RecordingLLM()
    llm.set_condense_response("压缩后的独立问题")
    workflow = QAWorkflow(retriever=retriever, llm=llm, timeout=30)

    history = [ChatMessage(role=MessageRole.USER, content="之前问过的问题")]
    result = await workflow.run(query="那 xx 呢？", chat_history=history, streaming=False)

    # 压缩 LLM 恰好被调用一次，prompt 里能看到 chat_history 内容和原始问题
    assert len(llm.received_prompts) == 1
    condense_prompt = llm.received_prompts[0]
    assert "之前问过的问题" in condense_prompt
    assert "那 xx 呢？" in condense_prompt

    # retrieve 阶段用的是压缩后的问题，不是原始 query
    assert retriever.calls == ["压缩后的独立问题"]

    # synthesize 阶段发给 LLM 的最终 prompt 里也是压缩后的问题
    assert llm.received_messages, "synthesize 阶段应该调用过一次 achat"
    final_prompt_content = llm.received_messages[-1][-1].content
    assert "压缩后的独立问题" in final_prompt_content
    assert "那 xx 呢？" not in final_prompt_content

    assert result.response.strip() != ""


@pytest.mark.asyncio
async def test_condense_question_falls_back_to_raw_query_on_llm_error():
    """压缩阶段 LLM 抛异常时不能让整个 workflow 挂掉：降级用原始 query 走
    检索和生成，照样能拿到正常结果。"""
    from handlers.qa_workflow import QAWorkflow

    nodes = [_make_node("一些内容")]
    retriever = FakeRetriever(nodes)
    llm = RecordingLLM()
    llm.set_condense_error(RuntimeError("condense boom"))
    workflow = QAWorkflow(retriever=retriever, llm=llm, timeout=30)

    history = [ChatMessage(role=MessageRole.USER, content="之前问过的问题")]
    result = await workflow.run(query="那 xx 呢？", chat_history=history, streaming=False)

    # 压缩确实被尝试调用过（不是被跳过），只是失败了
    assert len(llm.received_prompts) == 1
    # 降级：检索和最终结果都用原始 query
    assert retriever.calls == ["那 xx 呢？"]
    assert result.response.strip() != ""
    assert result.source_nodes == nodes


@pytest.mark.asyncio
async def test_condense_event_carries_query_and_context():
    """直接测 CondenseEvent 本身携带的数据结构，不经过完整 workflow 跑一遍。"""
    history = [ChatMessage(role=MessageRole.USER, content="之前的问题")]
    ev = CondenseEvent(query_str="压缩后的问题", chat_history=history, streaming=True)

    assert ev.query_str == "压缩后的问题"
    assert ev.chat_history == history
    assert ev.streaming is True
