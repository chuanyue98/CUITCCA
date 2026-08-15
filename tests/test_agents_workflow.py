"""backend/app/agents/agent_workflow.py 的测试。

覆盖：
1. 端到端的多轮工具调用编排：用 ``ScriptedFunctionCallingLLM``（本文件定义
   的假 ``FunctionCallingLLM``，按预先编排的脚本产出"调用工具"或"给出最终
   答案"的决策，不接入任何真实模型/网络）+ 真实 ``FunctionAgent`` 跑一遍
   单跳、多跳（先列目录、检索、检索不够换个关键词再查）两种场景。
2. 达到 max_iterations 上限时的优雅收尾：``truncated=True``，用已经收集到的
   信息生成收尾回答，不是硬抛异常炸穿请求。
3. 检索不到任何内容 / 最终答案为空文本时的兜底文案，跟 QAWorkflow 用同一个
   ``_FALLBACK_ANSWER``。
4. 会话历史被正确转发给底层 agent.run()。
5. Agent 运行异常（超时/运行时错误/其它异常）时降级返回兜底文案，不往上抛。
6. 流式路径 ``stream_agent_events``：token/tool_call/tool_result/done 四种
   事件按顺序产出。
7. ``extract_source_nodes``：从工具调用轨迹里解析出结构化来源，跳过报错的
   调用和非检索类工具，按 node_id 去重。
8. ``build_agent()``：默认挂载注册表里全部启用的工具；显式传 tool_names 时
   只挂一个子集。

第 5/6 类用一个轻量 FakeAgent/FakeHandler（跟 tests/test_graph_router.py 里
mock QAWorkflow handler 的 FakeHandler 是同一种模式），不需要真的构造一个会
超时的 FunctionAgent。
"""
import json
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from unittest.mock import patch

import pytest
from agents.agent_workflow import (
    _RUN_FAILED_MESSAGE,
    DEFAULT_MAX_TOOL_ROUNDS,
    ToolCallTrace,
    build_agent,
    extract_source_nodes,
    run_agent,
    stream_agent_events,
)
from handlers.qa_workflow import _FALLBACK_ANSWER
from llama_index.core.agent.workflow import AgentOutput, FunctionAgent
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from llama_index.core.llms.function_calling import FunctionCallingLLM
from llama_index.core.tools import BaseTool, FunctionTool, ToolSelection
from llama_index.core.workflow import WorkflowRuntimeError, WorkflowTimeoutError
from pydantic import PrivateAttr

import tests._pathsetup  # noqa: F401

# ── 测试专用的假 FunctionCallingLLM：按脚本推进，不接入真实模型 ────────


@dataclass
class ScriptedToolCall:
    tool_name: str
    tool_kwargs: dict


@dataclass
class ScriptedStep:
    """脚本里的一步：``tool_calls`` 非空表示这轮决策要调用这些工具；为空
    表示这轮直接给出最终文本答案 ``text``。"""

    tool_calls: list[ScriptedToolCall] = dc_field(default_factory=list)
    text: str = ""


class ScriptedFunctionCallingLLM(FunctionCallingLLM):
    """按预先编排的 ``ScriptedStep`` 列表逐步产出决策的假 LLM。

    只按调用顺序推进脚本，不解析传入的消息内容——``FunctionAgent`` 每轮决策
    只发起一次 achat/astream_chat 调用，脚本顺序天然对应"第几轮决策"。
    """

    _script: list[ScriptedStep] = PrivateAttr(default_factory=list)
    _step_index: int = PrivateAttr(default=0)

    def set_script(self, script: list[ScriptedStep]) -> None:
        self._script = script
        self._step_index = 0

    def _next_step(self) -> ScriptedStep:
        assert self._step_index < len(self._script), (
            f"ScriptedFunctionCallingLLM 脚本只有 {len(self._script)} 步，"
            f"但被调用了第 {self._step_index + 1} 次"
        )
        step = self._script[self._step_index]
        self._step_index += 1
        return step

    @staticmethod
    def _tool_calls_kwargs(step: ScriptedStep) -> dict:
        if not step.tool_calls:
            return {}
        return {
            "tool_calls": [
                {"id": f"call_{i}", "name": tc.tool_name, "kwargs": tc.tool_kwargs}
                for i, tc in enumerate(step.tool_calls)
            ]
        }

    @property
    def metadata(self):
        from llama_index.core.base.llms.types import LLMMetadata

        return LLMMetadata(is_function_calling_model=True, is_chat_model=True)

    def _prepare_chat_with_tools(
        self, tools, user_msg=None, chat_history=None, verbose=False,
        allow_parallel_tool_calls=False, tool_required=False, **kwargs,
    ):
        messages = list(chat_history or [])
        if user_msg is not None:
            if isinstance(user_msg, str):
                user_msg = ChatMessage(role=MessageRole.USER, content=user_msg)
            messages = [*messages, user_msg]
        return {"messages": messages}

    def get_tool_calls_from_response(self, response, error_on_no_tool_call=True, **kwargs):
        raw_calls = response.message.additional_kwargs.get("tool_calls", [])
        selections = [
            ToolSelection(tool_id=c["id"], tool_name=c["name"], tool_kwargs=c["kwargs"]) for c in raw_calls
        ]
        if not selections and error_on_no_tool_call:
            raise ValueError("ScriptedFunctionCallingLLM: 这一步脚本没有安排工具调用")
        return selections

    async def achat(self, messages, **kwargs) -> ChatResponse:
        step = self._next_step()
        message = ChatMessage(
            role=MessageRole.ASSISTANT, content=step.text, additional_kwargs=self._tool_calls_kwargs(step)
        )
        return ChatResponse(message=message)

    async def astream_chat(self, messages, **kwargs):
        step = self._next_step()
        additional_kwargs = self._tool_calls_kwargs(step)

        async def _gen():
            text = step.text or ""
            message = ChatMessage(role=MessageRole.ASSISTANT, content=text, additional_kwargs=additional_kwargs)
            yield ChatResponse(message=message, delta=text)

        return _gen()

    # FunctionAgent 的工具调用路径不会用到下面这些，占位满足抽象基类。
    def chat(self, messages, **kwargs):
        raise NotImplementedError

    def complete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError

    async def acomplete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError

    def stream_chat(self, messages, **kwargs):
        raise NotImplementedError

    def stream_complete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError

    async def astream_complete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError


def _search_result_json(node_id: str, text: str, file_name: str = "a.txt", score: float = 0.9) -> str:
    return json.dumps(
        {"query": "q", "result_count": 1, "results": [
            {"node_id": node_id, "score": score, "file_name": file_name, "source_url": None, "text": text}
        ]},
        ensure_ascii=False,
    )


async def _fake_search_tool(query: str, index_name: str | None = None, top_k: int | None = None) -> str:
    return _search_result_json("n1", f"关于 {query} 的内容")


async def _fake_list_kb_tool() -> str:
    return json.dumps({"index_count": 1, "indexes": [{"index_name": "idx1", "summary": "sum"}]}, ensure_ascii=False)


def _build_test_agent(
    llm: ScriptedFunctionCallingLLM, *, streaming: bool = False, timeout: float = 10
) -> FunctionAgent:
    tools: list[BaseTool | Callable] = [
        FunctionTool.from_defaults(async_fn=_fake_search_tool, name="search_knowledge_base", description="search"),
        FunctionTool.from_defaults(async_fn=_fake_list_kb_tool, name="list_knowledge_bases", description="list"),
    ]
    return FunctionAgent(tools=tools, llm=llm, system_prompt="sys", streaming=streaming, timeout=timeout)


# ── run_agent: 单跳 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_agent_single_tool_call_then_answers():
    llm = ScriptedFunctionCallingLLM()
    llm.set_script([
        ScriptedStep(tool_calls=[ScriptedToolCall("search_knowledge_base", {"query": "校训"})]),
        ScriptedStep(text="校训是成于大气 信达天下。"),
    ])
    agent = _build_test_agent(llm)

    result = await run_agent("学校的校训是什么？", agent=agent)

    assert result.response == "校训是成于大气 信达天下。"
    assert result.truncated is False
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "search_knowledge_base"
    assert len(result.source_nodes) == 1
    assert result.source_nodes[0].node.id_ == "n1"


# ── run_agent: 多跳（先列目录，再检索两次） ─────────────────────────


@pytest.mark.asyncio
async def test_run_agent_multi_hop_lists_then_searches_twice():
    llm = ScriptedFunctionCallingLLM()
    llm.set_script([
        ScriptedStep(tool_calls=[ScriptedToolCall("list_knowledge_bases", {})]),
        ScriptedStep(tool_calls=[ScriptedToolCall("search_knowledge_base", {"query": "第一次查询"})]),
        ScriptedStep(tool_calls=[ScriptedToolCall("search_knowledge_base", {"query": "换个角度再查"})]),
        ScriptedStep(text="综合两次检索结果给出的最终答案"),
    ])
    agent = _build_test_agent(llm)

    result = await run_agent("一个需要多跳才能答好的问题", agent=agent, max_iterations=6)

    assert result.response == "综合两次检索结果给出的最终答案"
    assert result.truncated is False
    assert [tc.tool_name for tc in result.tool_calls] == [
        "list_knowledge_bases", "search_knowledge_base", "search_knowledge_base",
    ]


# ── run_agent: 达到 max_iterations 上限时优雅收尾 ───────────────────


@pytest.mark.asyncio
async def test_run_agent_truncates_gracefully_at_max_iterations():
    llm = ScriptedFunctionCallingLLM()
    # llama_index 的 parse_agent_output 在每轮决策之后先判断是否已经达到
    # max_iterations，达到就直接转入 early-stopping 收尾，不会再把这一轮
    # 决定的工具调用派发出去执行——所以 max_iterations=2 时，第 1 轮的工具
    # 调用会真的执行，第 2 轮"决定"调用工具但还没来得及执行就被打断，直接
    # 触发第三步的收尾回答。脚本仍然要写 3 步：第 2 步的工具调用请求会被
    # 决策出来（消耗一次 achat 调用）但不会被真正执行。
    llm.set_script([
        ScriptedStep(tool_calls=[ScriptedToolCall("search_knowledge_base", {"query": "a"})]),
        ScriptedStep(tool_calls=[ScriptedToolCall("search_knowledge_base", {"query": "b"})]),
        ScriptedStep(text="轮次已到上限，基于已查到的信息给出的收尾回答"),
    ])
    agent = _build_test_agent(llm)

    result = await run_agent("一个模型会不停检索的问题", agent=agent, max_iterations=2)

    assert result.truncated is True
    assert result.response == "轮次已到上限，基于已查到的信息给出的收尾回答"
    # 撞上限前那次真正执行完的工具调用轨迹应该还在，不能因为截断就把已经
    # 做的工作丢掉。
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_kwargs == {"query": "a"}


# ── run_agent: 空文本兜底 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_agent_falls_back_when_final_answer_is_empty_text():
    llm = ScriptedFunctionCallingLLM()
    llm.set_script([ScriptedStep(text="   ")])  # 模型直接给了个空白答案，没调用任何工具
    agent = _build_test_agent(llm)

    result = await run_agent("问题", agent=agent)

    assert result.response == _FALLBACK_ANSWER
    assert result.tool_calls == []


# ── run_agent: 会话历史转发 / 护栏参数转发 ──────────────────────────


class _FakeAgentHandler:
    def __init__(self, events, result=None, exception=None):
        self._events = events
        self._result = result
        self._exception = exception

    async def stream_events(self):
        for ev in self._events:
            yield ev

    def __await__(self):
        async def _inner():
            if self._exception is not None:
                raise self._exception
            return self._result

        return _inner().__await__()


class _FakeAgent:
    """跟 tests/test_graph_router.py mock QAWorkflow handler 的 FakeHandler
    是同一种模式：不构造真实 FunctionAgent，只关心 run_agent()/
    stream_agent_events() 怎么调用 .run() 以及怎么处理 handler 的结果/异常。
    """

    def __init__(self, handler_factory):
        self.run_calls: list[dict] = []
        self._handler_factory = handler_factory

    def run(self, **kwargs):
        self.run_calls.append(kwargs)
        return self._handler_factory()


def _agent_output(text: str) -> AgentOutput:
    return AgentOutput(
        response=ChatMessage(role=MessageRole.ASSISTANT, content=text),
        tool_calls=[],
        raw=None,
        current_agent_name="Agent",
    )


@pytest.mark.asyncio
async def test_run_agent_forwards_chat_history_and_guardrail_kwargs():
    history = [ChatMessage(role=MessageRole.USER, content="之前问过的问题")]
    fake_agent = _FakeAgent(lambda: _FakeAgentHandler(events=[], result=_agent_output("answer")))

    await run_agent("追问", chat_history=history, agent=fake_agent, max_iterations=3)

    assert len(fake_agent.run_calls) == 1
    call_kwargs = fake_agent.run_calls[0]
    assert call_kwargs["user_msg"] == "追问"
    assert call_kwargs["chat_history"] == history
    assert call_kwargs["max_iterations"] == 3
    assert call_kwargs["early_stopping_method"] == "generate"


@pytest.mark.asyncio
async def test_run_agent_default_max_iterations_is_module_constant():
    fake_agent = _FakeAgent(lambda: _FakeAgentHandler(events=[], result=_agent_output("answer")))

    await run_agent("问题", agent=fake_agent)

    assert fake_agent.run_calls[0]["max_iterations"] == DEFAULT_MAX_TOOL_ROUNDS


# ── run_agent: 异常/超时降级 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_agent_falls_back_on_timeout():
    fake_agent = _FakeAgent(lambda: _FakeAgentHandler(events=[], exception=WorkflowTimeoutError("timed out")))

    result = await run_agent("问题", agent=fake_agent)

    assert result.response == _FALLBACK_ANSWER
    assert result.truncated is True


@pytest.mark.asyncio
async def test_run_agent_falls_back_on_runtime_error():
    fake_agent = _FakeAgent(lambda: _FakeAgentHandler(events=[], exception=WorkflowRuntimeError("boom")))

    result = await run_agent("问题", agent=fake_agent)

    assert result.response == _FALLBACK_ANSWER
    assert result.truncated is True


@pytest.mark.asyncio
async def test_run_agent_falls_back_on_generic_exception():
    fake_agent = _FakeAgent(lambda: _FakeAgentHandler(events=[], exception=RuntimeError("llm decision call failed")))

    result = await run_agent("问题", agent=fake_agent)

    assert result.response == _FALLBACK_ANSWER


# ── stream_agent_events ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_agent_events_yields_token_tool_call_tool_result_done_in_order():
    llm = ScriptedFunctionCallingLLM()
    llm.set_script([
        ScriptedStep(tool_calls=[ScriptedToolCall("search_knowledge_base", {"query": "校训"})]),
        ScriptedStep(text="流式最终答案"),
    ])
    agent = _build_test_agent(llm, streaming=True)

    events = [ev async for ev in stream_agent_events("学校的校训是什么？", agent=agent)]
    event_types = [ev["type"] for ev in events]

    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert event_types[-1] == "done"
    assert event_types.index("tool_call") < event_types.index("tool_result")

    done_event = events[-1]
    assert done_event["response"] == "流式最终答案"
    assert done_event["truncated"] is False
    assert done_event["tool_call_count"] == 1

    token_events = [ev for ev in events if ev["type"] == "token"]
    assert "".join(ev["content"] for ev in token_events) == "流式最终答案"


@pytest.mark.asyncio
async def test_stream_agent_events_yields_error_event_on_timeout():
    fake_agent = _FakeAgent(lambda: _FakeAgentHandler(events=[], exception=WorkflowTimeoutError("timed out")))

    events = [ev async for ev in stream_agent_events("问题", agent=fake_agent)]

    # 刻意不是 _FALLBACK_ANSWER（"我还不知道"）：那句话的语义是"知识库里没有
    # 这个内容"，而超时/限流是"这次请求没跑完"，对用户意味着完全不同的下一步。
    # 实测里连续提问打爆 LLM 服务商 rpm 配额（429）时显示"我还不知道"，会让人
    # 误以为知识库缺内容。
    assert events == [{"type": "error", "message": _RUN_FAILED_MESSAGE}]
    assert _RUN_FAILED_MESSAGE != _FALLBACK_ANSWER


# ── extract_source_nodes ─────────────────────────────────────────────


def test_extract_source_nodes_parses_search_and_source_lookup_tools():
    search_trace = ToolCallTrace(
        tool_name="search_knowledge_base", tool_kwargs={}, is_error=False,
        output=_search_result_json("n1", "检索到的内容"),
    )
    lookup_trace = ToolCallTrace(
        tool_name="get_document_chunks_by_source", tool_kwargs={}, is_error=False,
        output=json.dumps({"source": "a.txt", "chunk_count": 1, "chunks": [
            {"node_id": "n2", "file_name": "a.txt", "source_url": None, "text": "原文片段"},
        ]}, ensure_ascii=False),
    )

    nodes = extract_source_nodes([search_trace, lookup_trace])

    assert {n.node.id_ for n in nodes} == {"n1", "n2"}


def test_extract_source_nodes_skips_error_and_non_retrieval_tools():
    error_trace = ToolCallTrace(
        tool_name="search_knowledge_base", tool_kwargs={}, is_error=True,
        output=_search_result_json("n1", "本不该出现"),
    )
    other_tool_trace = ToolCallTrace(
        tool_name="get_current_datetime", tool_kwargs={}, is_error=False,
        output=json.dumps({"date": "2026-08-08"}, ensure_ascii=False),
    )

    nodes = extract_source_nodes([error_trace, other_tool_trace])

    assert nodes == []


def test_extract_source_nodes_dedupes_by_node_id_keeping_first():
    trace1 = ToolCallTrace(
        tool_name="search_knowledge_base", tool_kwargs={}, is_error=False,
        output=_search_result_json("n1", "第一次看到的内容"),
    )
    trace2 = ToolCallTrace(
        tool_name="search_knowledge_base", tool_kwargs={}, is_error=False,
        output=_search_result_json("n1", "第二次看到的内容"),
    )

    nodes = extract_source_nodes([trace1, trace2])

    assert len(nodes) == 1
    assert nodes[0].node.get_content() == "第一次看到的内容"


def test_extract_source_nodes_handles_malformed_json_gracefully():
    bad_trace = ToolCallTrace(tool_name="search_knowledge_base", tool_kwargs={}, is_error=False, output="not json")
    assert extract_source_nodes([bad_trace]) == []


# ── build_agent ───────────────────────────────────────────────────────


def test_build_agent_uses_all_enabled_default_tools():
    from llama_index.core.llms import MockLLM

    agent = build_agent(llm=MockLLM())
    tool_names = {t.metadata.get_name() for t in agent.tools}

    assert tool_names == {
        "search_knowledge_base", "list_knowledge_bases", "get_document_chunks_by_source", "get_current_datetime",
    }


def test_build_agent_respects_explicit_tool_names_subset():
    from llama_index.core.llms import MockLLM

    agent = build_agent(llm=MockLLM(), tool_names=["list_knowledge_bases"])
    tool_names = {t.metadata.get_name() for t in agent.tools}

    assert tool_names == {"list_knowledge_bases"}


def test_build_agent_uses_settings_llm_when_not_provided():
    from llama_index.core.llms import MockLLM
    from llama_index.core.settings import Settings

    with patch.object(Settings, "_llm", MockLLM()):
        agent = build_agent()

    assert isinstance(agent.llm, MockLLM)
