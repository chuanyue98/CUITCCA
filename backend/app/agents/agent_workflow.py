"""Agent 编排层：把 ``agents/tools.py`` 的工具注册表接到 LlamaIndex 的
``FunctionAgent`` 上，让模型自己决定要不要调用工具、调用几次、调用哪个。

## 跟 QAWorkflow 的分工：新增一条路径，不改/不替换现有的

``handlers/qa_workflow.py`` 的 ``QAWorkflow`` 是现有 7 个端点的低延迟主路径：
单轮问答零额外 LLM 调用（``condense_question`` 在没有 ``chat_history`` 时
直接透传），``retrieve`` 只检索一次，``synthesize`` 直接把检索到的内容喂给
LLM 生成答案——整条链路对"要不要检索""检索几次"没有任何决策开销。

这里的 ``FunctionAgent`` 编排至少比 QAWorkflow 多付一次 LLM 往返（"要不要
调用工具、调用哪个"这次决策本身就是一次 LLM 调用），命中多跳场景时还会
更多——用延迟和成本换来的是 ``qa_workflow.py`` 模块 docstring"检索迭代
上限"一节里提到、故意没做的能力：模型可以先列目录、检索一次发现不够、换个
关键词或指定索引再查一次，直到有把握回答或者达到轮次上限。

**不是所有查询都应该走这条路**：多数校园知识库问答是"查一次就能答"的简单
事实问句，QAWorkflow 已经用最低延迟覆盖了这部分；只有"需要先弄清楚有哪些
资料再决定查哪个""第一次查不到需要换个角度重试""需要追问原文核实"这类
真正需要多跳的场景，多付的那次决策开销才值得。所以两条路径都留着，挂在不同
端点（``/graph/agent_chat*``，见 ``router/graph.py``），不是拿 Agent 版本
覆盖或内联进 QAWorkflow——``/graph/agent`` 那个历史端点名字带"agent"但其实
是 QAWorkflow 的别名，命名是历史遗留，不能改（会破坏既有测试），新端点特意
换了个名字避免和它混淆。

## 为什么用 FunctionAgent 而不是 AgentWorkflow/ReActAgent

- ``AgentWorkflow`` 是给"多个具名 agent 互相 handoff"场景用的编排层（见
  ``llama_index.core.agent.workflow.multi_agent_workflow``）；这里只有一个
  角色（"校园知识库问答助手"），不需要 handoff，直接用单个 ``FunctionAgent``
  更直接——``FunctionAgent`` 本身就是一个 ``Workflow`` 子类，能独立
  ``.run()``/``.stream_events()``，不需要外面再套一层 ``AgentWorkflow``。
- ``ReActAgent`` 是给不支持原生 function calling 的 LLM 用的（靠 prompt
  里的 "Thought/Action/Observation" 格式模拟工具调用，容易被自由格式输出
  带偏）。项目配置的 LLM 走 OpenAI-like 接口（见
  ``configs/llm_predictor.py``），支持原生 function calling，用
  ``FunctionAgent`` 更可靠，不需要 ReAct 那套格式解析兜底。

## 护栏怎么落地（不是自己从头写一套，是用 llama_index 内置机制）

- **最大工具调用轮数**：不是自己数轮数再手动截断，用
  ``FunctionAgent.run(max_iterations=..., early_stopping_method="generate")``
  ——这是 ``llama_index.core.agent.workflow.base_agent`` 内置的机制：每次
  LLM 决策（``parse_agent_output`` step）都会把 ``num_iterations`` 加一，
  达到 ``max_iterations`` 时不是硬抛异常炸穿请求（那是 ``early_stopping_
  method="force"`` 的默认行为），而是 ``"generate"`` 模式会额外调用一次 LLM，
  把"已经收集到的信息 + 明确说明轮次已到上限"喂给它，生成一个基于现有信息的
  收尾回答——这正是"优雅收尾"要求的行为，直接复用官方实现比自己在这层加一个
  计数器可靠（官方实现覆盖了并行工具调用等边界情况）。
- **超时**：``FunctionAgent(timeout=...)`` 是标准 ``Workflow`` 的
  ``timeout`` kwarg，超时抛 ``workflows.errors.WorkflowTimeoutError``，
  ``run_agent()``/``stream_agent_events()`` 捕获它，返回和 QAWorkflow 请求
  失败时同一个兜底文案（见下面"降级路径"）。
- **引用约束**：``configs/config.py`` 的 ``Prompts.AGENT_SYSTEM_PROMPT``
  明确要求"没检索到就如实说不知道，不要编造"；真正的兜底不完全依赖模型
  听话——``_FALLBACK_ANSWER`` 直接复用 ``handlers.qa_workflow`` 里那个常量，
  跟 QAWorkflow/``/query`` 等端点保持完全一致的兜底文案，不是另写一句不一样
  的话。
- **LLM/工具调用失败的降级**：单个工具调用抛异常时，llama_index 内置的
  ``_call_tool`` 会捕获异常包装成 ``ToolOutput(is_error=True, content=str(e))``
  反馈给模型（模型可以据此换个思路重试，不会导致整个请求失败）——
  ``agents/tools.py`` 里的工具函数自己也做了一层 try/except 返回结构化错误
  JSON，是双保险，不是重复劳动：工具内部的 try/except 能给模型一个更友好、
  可读的错误说明，llama_index 那层 try/except 是兜底，防止工具实现本身有
  遗漏。如果是决策 LLM 本身调用失败（网络抖动等），异常会从 ``handler``
  往上抛，``run_agent()``/路由端点捕获后返回统一的"出错了，请稍后再试一下
  吧"——跟 ``router/graph.py`` 现有端点处理 ``QAWorkflow`` 异常的方式一致。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from agents.tools import GET_DOCUMENT_CHUNKS_BY_SOURCE, SEARCH_KNOWLEDGE_BASE, get_default_registry
from configs.config import Prompts
from handlers.qa_workflow import _FALLBACK_ANSWER
from llama_index.core.agent.workflow import (
    AgentOutput,
    AgentStream,
    FunctionAgent,
    ToolCall,
    ToolCallResult,
)
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.llms import LLM
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.settings import Settings
from llama_index.core.workflow import WorkflowRuntimeError, WorkflowTimeoutError

logger = logging.getLogger(__name__)
_RUN_FAILED_MESSAGE = "刚才没能查完，请稍后再试一次。"
"""运行失败（超时 / LLM 调用异常 / 服务商限流等）时给用户的话。

刻意**不复用** ``_FALLBACK_ANSWER``（"我还不知道，请反馈给我吧"）：那句话的
语义是"知识库里没有这个内容"，而这里是"这次请求没跑完"——两者对用户意味着
完全不同的下一步（前者别再问了、换个渠道；后者过一会儿重试就行）。实测中
连续提问打爆了 LLM 服务商的 rpm 配额（429），界面显示的却是"我还不知道"，
会让人以为知识库缺内容，其实只要等一会儿重试即可。
"""


DEFAULT_MAX_TOOL_ROUNDS = 6
"""最大工具调用轮数（对应 FunctionAgent.run 的 max_iterations）。6 是"给够
多跳空间、又不至于让一个请求无限跑下去"的经验值：目录 1 轮 + 检索 1-2 轮 +
换角度重试 1-2 轮，通常够覆盖真实的多跳场景；评测阶段如果发现常规问题也频繁
撞到这个上限，应该先看是不是工具描述没写清楚导致模型瞎试，而不是简单调大
这个数字。"""

DEFAULT_AGENT_TIMEOUT = 90.0
"""秒。比 QAWorkflow 常用的 60 秒稍宽——Agent 路径天然比单次检索多至少一次
LLM 决策往返，命中多跳时还会更多，60 秒对多轮场景偏紧。"""

AGENT_SYSTEM_PROMPT: str = Prompts.AGENT_SYSTEM_PROMPT.value.get_template()


@dataclass
class ToolCallTrace:
    """一次工具调用的精简记录，供调用方（路由端点）展示"Agent 都做了什么"、
    以及从检索类工具的输出里抠出结构化来源用于引用溯源。"""

    tool_name: str
    tool_kwargs: dict[str, Any]
    output: str
    is_error: bool


@dataclass
class AgentRunResult:
    """``run_agent()`` 跑完之后的最终结果。"""

    response: str
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    truncated: bool = False
    """True 表示这次回答是因为撞到 max_iterations 上限、靠
    early_stopping_method="generate" 生成的收尾回答，不是模型主动认为
    "已经查够了"才停下来的——调用方可以据此在前端提示"这个回答可能不完整"。
    """
    source_nodes: list[NodeWithScore] = field(default_factory=list)
    """从检索类工具调用结果里抠出来的来源节点，见 ``extract_source_nodes``。
    跟 ``QAWorkflowResult.source_nodes`` 是同一个类型——路由端点可以直接把它
    塞进现有 ``/query_sources`` 用的那个 TTLCache，不用为 Agent 路径另起一套
    "查最近来源"的接口。"""


def extract_source_nodes(tool_calls: list[ToolCallTrace]) -> list[NodeWithScore]:
    """把 ``search_knowledge_base``/``get_document_chunks_by_source`` 两个
    工具返回的 JSON（见 ``agents/tools.py`` 模块 docstring）解析成
    ``NodeWithScore`` 列表。

    只挑这两个工具的输出，因为只有它们的返回值里带着"知识库原文片段 +
    node_id/file_name/source_url"这种可以合理当作"引用来源"的结构；
    ``list_knowledge_bases``/``get_current_datetime`` 返回的是目录/日期这类
    元信息，不是回答内容的依据，不应该被当成"来源"展示给用户。

    按 node_id 去重、保留首次出现的顺序——同一个 chunk 完全可能在"先检索、
    再按来源取原文核实"这类多跳场景里被拿到两次，不去重会让来源列表里出现
    重复条目。
    """
    nodes: list[NodeWithScore] = []
    seen_ids: set[str] = set()
    for trace in tool_calls:
        if trace.is_error or trace.tool_name not in (SEARCH_KNOWLEDGE_BASE, GET_DOCUMENT_CHUNKS_BY_SOURCE):
            continue
        try:
            payload = json.loads(trace.output)
        except (TypeError, ValueError):
            continue
        entries = payload.get("results" if trace.tool_name == SEARCH_KNOWLEDGE_BASE else "chunks") or []
        for entry in entries:
            node_id = entry.get("node_id")
            if not node_id or node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            metadata = {
                key: value
                for key, value in (("file_name", entry.get("file_name")), ("source_url", entry.get("source_url")))
                if value
            }
            nodes.append(
                NodeWithScore(
                    node=TextNode(id_=node_id, text=entry.get("text", ""), metadata=metadata),
                    score=entry.get("score"),
                )
            )
    return nodes


def build_agent(
    *,
    llm: LLM | None = None,
    tool_names: list[str] | None = None,
    timeout: float | None = DEFAULT_AGENT_TIMEOUT,
) -> FunctionAgent:
    """构造一个挂好默认工具集的 ``FunctionAgent``。

    ``tool_names=None`` 时用注册表里当前"启用"的全部工具（见
    ``agents/registry.py`` 的 enable/disable 语义）；显式传子集可以让某个
    调用方只暴露部分工具（比如只读端点只给检索类工具，不给未来可能加的
    写操作工具），不需要新建一个 registry 实例。
    """
    registry = get_default_registry()
    tools = registry.build_tools(tool_names)
    return FunctionAgent(
        name="cuitcca_campus_agent",
        description="成都信息工程大学校园知识库问答 Agent，可多轮调用检索类工具后再作答。",
        tools=tools,
        llm=llm or Settings.llm,
        system_prompt=AGENT_SYSTEM_PROMPT,
        timeout=timeout,
    )


def _tool_call_result_to_trace(ev: ToolCallResult) -> ToolCallTrace:
    output = ev.tool_output
    content = output.content if output is not None else ""
    is_error = bool(output is not None and output.is_error)
    return ToolCallTrace(tool_name=ev.tool_name, tool_kwargs=ev.tool_kwargs, output=content, is_error=is_error)


def _agent_output_text(output: AgentOutput) -> str:
    text = (output.response.content or "").strip()
    return text or _FALLBACK_ANSWER


def _detect_truncation(agent_output_event_count: int, max_iterations: int) -> bool:
    """判断这次运行是不是被 max_iterations 上限截断的。

    llama_index ``base_agent.parse_agent_output`` 每次 LLM 决策（不管这轮
    要不要调用工具）都会先把 ``num_iterations`` 加一，写一次 ``AgentOutput``
    事件到流里（见 ``run_agent_step``），再判断是否达到上限；正常收尾（模型
    自己决定"不用再调用工具了"）时，这个已经写过的 ``AgentOutput`` 直接就是
    最终结果，不会再多写一次。只有撞到 ``max_iterations`` 上限、走
    ``early_stopping_method="generate"`` 时，``_generate_early_stopping_
    response`` 才会**额外**发起一次总结性 LLM 调用并再写一次 ``AgentOutput``
    事件——所以正常完成时观察到的 ``AgentOutput`` 事件数永远 <=
    ``max_iterations``，被截断时永远是 ``max_iterations + 1``。用这个事件计数
    差异来判断，不用去改 llama_index 源码加自定义标记，也不用假设
    ``AgentOutput.tool_calls`` 字段的内容（两条路径其实都会把累计的工具调用
    记录塞进这个字段，不能拿它是否为空来判断，试过、不准）。
    """
    return agent_output_event_count > max_iterations


async def run_agent(
    query: str,
    *,
    chat_history: list[ChatMessage] | None = None,
    agent: FunctionAgent | None = None,
    max_iterations: int = DEFAULT_MAX_TOOL_ROUNDS,
) -> AgentRunResult:
    """非流式跑一次 Agent 问答，返回最终回答 + 工具调用轨迹。

    ``agent`` 可以显式注入（测试用，避免每次都要构造真实工具/真实 LLM），
    不传则用 ``build_agent()`` 的默认配置——跟 ``QAWorkflow.__init__`` 支持
    注入 ``retriever=``/``llm=`` 是同一个测试友好模式。
    """
    agent = agent or build_agent()
    handler = agent.run(
        user_msg=query,
        chat_history=list(chat_history or []),
        max_iterations=max_iterations,
        early_stopping_method="generate",
    )

    tool_calls: list[ToolCallTrace] = []
    agent_output_events = 0
    try:
        async for ev in handler.stream_events():
            if isinstance(ev, ToolCallResult):
                tool_calls.append(_tool_call_result_to_trace(ev))
            elif isinstance(ev, AgentOutput):
                agent_output_events += 1
        output: AgentOutput = await handler
    except (WorkflowTimeoutError, WorkflowRuntimeError):
        logger.warning("Agent 运行超时或撞到运行时错误，降级返回兜底文案。", exc_info=True)
        return AgentRunResult(
            response=_FALLBACK_ANSWER, tool_calls=tool_calls, truncated=True,
            source_nodes=extract_source_nodes(tool_calls),
        )
    except Exception:
        logger.exception("Agent 运行失败（决策 LLM 调用异常等），降级返回兜底文案。")
        return AgentRunResult(
            response=_FALLBACK_ANSWER, tool_calls=tool_calls, truncated=True,
            source_nodes=extract_source_nodes(tool_calls),
        )

    truncated = _detect_truncation(agent_output_events, max_iterations)
    return AgentRunResult(
        response=_agent_output_text(output),
        tool_calls=tool_calls,
        truncated=truncated,
        source_nodes=extract_source_nodes(tool_calls),
    )


async def stream_agent_events(
    query: str,
    *,
    chat_history: list[ChatMessage] | None = None,
    agent: FunctionAgent | None = None,
    max_iterations: int = DEFAULT_MAX_TOOL_ROUNDS,
):
    """流式跑一次 Agent 问答，把 token / 工具调用过程都作为事件 yield 出去。

    每个事件是一个 dict，``type`` 取值：
    - ``token``：最终答案的增量文本（``content`` 字段），路由端点用它拼出
      流式的用户可见文本。
    - ``tool_call``：模型决定调用某个工具（``tool_name``/``tool_kwargs``），
      在工具真正执行之前发出。
    - ``tool_result``：工具执行完毕（``tool_name``/``is_error``/``output``），
      ``output`` 是工具返回的 JSON 字符串（见 ``agents/tools.py`` 模块
      docstring），调用方可以直接 ``json.loads`` 解析出结构化来源。
    - ``done``：整个请求结束，带上最终 ``response``、精简的 ``tool_calls``
      轨迹、``truncated`` 标记。
    - ``error``：出错兜底，``message`` 是兜底文案，跟非流式路径用同一个
      ``_FALLBACK_ANSWER``。

    工具调用类事件（``ToolCall``/``ToolCallResult``）是 llama_index
    ``FunctionAgent`` 无条件写进事件流的（不受 ``FunctionAgent.streaming``
    参数影响，那个参数只控制最终答案要不要按 token 增量输出），这里原样
    转发出去，不是自己额外埋点算出来的。
    """
    agent = agent or build_agent()
    handler = agent.run(
        user_msg=query,
        chat_history=list(chat_history or []),
        max_iterations=max_iterations,
        early_stopping_method="generate",
    )

    tool_calls: list[ToolCallTrace] = []
    agent_output_events = 0
    try:
        async for ev in handler.stream_events():
            if isinstance(ev, AgentStream):
                if ev.delta:
                    yield {"type": "token", "content": ev.delta}
            elif isinstance(ev, ToolCall):
                yield {"type": "tool_call", "tool_name": ev.tool_name, "tool_kwargs": ev.tool_kwargs}
            elif isinstance(ev, ToolCallResult):
                trace = _tool_call_result_to_trace(ev)
                tool_calls.append(trace)
                yield {
                    "type": "tool_result",
                    "tool_name": trace.tool_name,
                    "is_error": trace.is_error,
                    "output": trace.output,
                }
            elif isinstance(ev, AgentOutput):
                agent_output_events += 1
        output: AgentOutput = await handler
    except (WorkflowTimeoutError, WorkflowRuntimeError):
        logger.warning("Agent 流式运行超时或撞到运行时错误，降级返回兜底文案。", exc_info=True)
        yield {"type": "error", "message": _RUN_FAILED_MESSAGE}
        return
    except Exception:
        logger.exception("Agent 流式运行失败（决策 LLM 调用异常等），降级返回兜底文案。")
        yield {"type": "error", "message": _RUN_FAILED_MESSAGE}
        return

    truncated = _detect_truncation(agent_output_events, max_iterations)
    response_text = _agent_output_text(output)
    yield {
        "type": "done",
        "response": response_text,
        "tool_call_count": len(tool_calls),
        "truncated": truncated,
    }
