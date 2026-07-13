"""基于 llama_index.core.workflow 的问答工作流（Phase 3，新增/验证性质）。

**不替换** ``handlers/graph_builder.py`` 里现有的 query engine / chat engine
链路——``router/graph.py`` 的 7 个现有端点原封不动继续用那一套。这里是一条
独立、并行的新问答路径，用 llama_index 官方推荐的 Workflow 原语（显式
``Event`` 在 step 之间传数据、``ctx.write_event_to_stream`` + 原生
``stream_events()`` 做流式）重新搭一遍同样的"检索 -> 生成"链路，验证迁移到
Workflow 是否可行、检索质量是否不低于现有基线，为后续是否正式切换积累证据。

## 索引选择逻辑：复用，不重新发明

``_build_retriever()`` 和 ``graph_builder._build_query_engine()`` 走的是**同一
套**索引数量分支（0 个 / 1 个 / 多个）和**同一个** ``LLMSingleSelector``：
0 个索引用一个返回空结果的占位 retriever（对应 ``MultiIndexQueryEngine`` 在
无索引时的"Empty Response"行为）；1 个索引直接 ``index.as_retriever(...)``；
多个索引用 ``RouterRetriever``（``RetrieverTool`` + 同一个
``LLMSingleSelector.from_defaults()``）——这不是重新实现路由算法，只是把
``RouterQueryEngine``/``QueryEngineTool`` 换成检索层的对应物
``RouterRetriever``/``RetrieverTool``，选择逻辑（哪个索引、用哪个 selector）
完全没变。

## 流式实现：Workflow 原生机制，不复用 chat_engine 的 response_gen 那一套

``router/graph.py`` 的 ``/chat_stream`` 端点踩过一个真实的坑：
``astream_chat()`` 产出的响应只有 ``async_response_gen()`` 能正确产出
token，同步的 ``response_gen`` 会拿到空生成器。为了不在新代码里搬运同一类
"同步/异步生成器分裂"的问题，这里的流式**完全不经过**
response_synthesizer/chat_engine 那套 response_gen 属性——``synthesize`` step
直接调用 ``llm.astream_chat()`` 拿到 token 级别的异步生成器，每个 delta 通过
``ctx.write_event_to_stream(TokenEvent(...))`` 广播出去，调用方用
``handler.stream_events()`` 消费，链路里只有一种"异步生成器"，没有第二套容易
被用错的同步接口。

## 检索迭代上限：为 multi-hop 留的钩子，这一版只用 1 次

``max_retrieval_iterations`` 参数现在唯一生效的取值是 1（``retrieve`` step
只调用一次检索）。传大于 1 的值目前会在日志里提示"暂未实现多轮检索"但仍然
只跑一次——不假装支持、不静默丢弃这个语义。评测阶段的经验是这类迭代不建议
超过 3 轮（收益递减、延迟线性增加），所以把参数留出来但不在这一版实现自适应
重新检索逻辑，避免为了凑功能牺牲质量。

## 工具选择：这一版故意不做

``synthesize`` step 之前特意没有搭一个"模型自己决定要不要调用某个工具"的
Agent 决策循环——现在除了检索之外没有其它真实工具可选（MCP 工具要等
Phase 4），做一个只有单一选项的"决策"纯粹空转、没有意义。见
``synthesize`` 方法开头的注释：未来要接入工具选择时，在 ``RetrieveEvent``
之后、生成回答之前，把这一段换成 ``AgentWorkflow``/``FunctionAgent`` 来做。

## 多轮对话：目前只是"把历史塞进 prompt"，不做问题压缩

可以传 ``chat_history``（``list[ChatMessage]``），会作为对话历史一并传给
LLM。但**没有**复刻 ``CondenseQuestionChatEngine`` 那套"先把追问压缩成独立
问题、再拿压缩后的问题去检索"的逻辑——检索阶段用的还是原始 ``query`` 字符
串。这意味着依赖代词/省略的追问（"那 xx 呢？"）在这条新路径上检索效果会比
现有 ``/chat_stream`` 差。这是已知、故意接受的差距，不是遗漏；真正要在多轮
场景达到现有 chat_engine 的水平，需要在 ``retrieve`` step 前加一个"问题改写"
step，留给后续加强。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

# DEFAULT_SIMILARITY_TOP_K 故意不在这里用 `from configs.load_env import X` 直接
# 绑定，理由见 handlers/graph_builder.py 顶部同样的说明——那样绑定会让
# reload_env_variables() 之后这个值就再也感知不到环境变量变化了。改成
# `import configs.load_env as load_env` + 使用处 `load_env.X` 属性访问，才能
# 在每次真正调用时读到最新值。
import configs.load_env as load_env
from configs.config import Prompts
from handlers.index_crud import indexes
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.llms import LLM
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.settings import Settings
from llama_index.core.tools import RetrieverTool
from llama_index.core.workflow import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)
from pydantic import Field
from utils.llama import index_description

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIEVAL_ITERATIONS = 1
"""检索迭代上限的钩子。当前唯一实现的行为是跑 1 轮检索；这个参数为未来
multi-hop/自适应检索（第一轮结果不够时改写问题重新检索）预留，评测阶段的
经验建议这类迭代不超过 3 轮。见模块 docstring。"""

_FALLBACK_ANSWER = "我还不知道，请反馈给我吧"
"""与现有 /query、websocket /query 端点里 Empty Response 的兜底文案保持一致。"""


class RetrieveEvent(Event):
    """retrieve step 的输出：本轮检索到的 nodes + 本次问答的上下文。"""

    nodes: list[NodeWithScore]
    query_str: str
    chat_history: list[ChatMessage] = Field(default_factory=list)
    streaming: bool = False


class TokenEvent(Event):
    """流式合成过程中，每个增量 token 通过 ctx.write_event_to_stream 广播。

    调用方用 ``handler.stream_events()`` 消费，按类型过滤只处理
    ``TokenEvent``，直到收到 ``StopEvent``。这是 Workflow 官方推荐的流式
    机制，见模块 docstring 里为什么不复用 chat_engine 的 response_gen。
    """

    token: str


@dataclass
class QAWorkflowResult:
    """StopEvent.result 携带的最终结果。"""

    response: str
    source_nodes: list[NodeWithScore]


class _EmptyRetriever(BaseRetriever):
    """没有任何索引时的占位 retriever，返回空结果。

    镜像 ``graph_builder.MultiIndexQueryEngine`` 在 ``indexes_snapshot=[]``
    时的行为——最终都是"检索不到任何内容 -> 兜底文案"。
    """

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return []

    async def _aretrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return []


def _build_retriever(top_k: int | None = None) -> BaseRetriever:
    """复用 graph_builder._build_query_engine 的索引选择逻辑，只取 retriever。

    见模块 docstring"索引选择逻辑：复用，不重新发明"一节。

    ``top_k`` 默认 None：沿用 ``load_env.DEFAULT_SIMILARITY_TOP_K``（生产环境
    的 ``QAWorkflow`` 就是这么调用的，不传参）。评测脚本
    ``evals/run_workflow_retrieval_eval.py`` 需要按 CLI 的 ``--top-k`` 覆盖，
    所以这里留了这个可选参数——``QAWorkflow`` 本身不新增这个旋钮，`retrieve`
    step 仍然零参数调用 ``_build_retriever()``。
    """
    effective_top_k = top_k if top_k is not None else load_env.DEFAULT_SIMILARITY_TOP_K
    indexes_snapshot = list(indexes)
    if not indexes_snapshot:
        return _EmptyRetriever()
    if len(indexes_snapshot) == 1:
        return indexes_snapshot[0].as_retriever(similarity_top_k=effective_top_k)

    retriever_tools = [
        RetrieverTool.from_defaults(
            retriever=index.as_retriever(similarity_top_k=effective_top_k),
            description=index_description(index),
        )
        for index in indexes_snapshot
    ]
    from llama_index.core.retrievers import RouterRetriever

    return RouterRetriever.from_defaults(
        retriever_tools=retriever_tools,
        selector=LLMSingleSelector.from_defaults(),
        # select_multi=False：和 graph_builder._build_query_engine 里
        # RouterQueryEngine 的取舍一致，见那边的注释。
        select_multi=False,
    )


class QAWorkflow(Workflow):
    """两步问答工作流：retrieve -> synthesize。

    依赖（retriever / llm）都可以显式注入（测试用，避免碰全局 ``Settings``
    单例或需要真实索引），不传则在运行时分别取 ``_build_retriever()`` 和
    ``Settings.llm``。
    """

    def __init__(
        self,
        *args,
        retriever: BaseRetriever | None = None,
        llm: LLM | None = None,
        max_retrieval_iterations: int = DEFAULT_MAX_RETRIEVAL_ITERATIONS,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._retriever = retriever
        self._llm = llm
        self.max_retrieval_iterations = max_retrieval_iterations

    @step
    async def retrieve(self, ctx: Context, ev: StartEvent) -> RetrieveEvent:
        query_str: str = ev.query
        chat_history: list[ChatMessage] = list(getattr(ev, "chat_history", None) or [])
        streaming: bool = bool(getattr(ev, "streaming", False))

        if self.max_retrieval_iterations > 1:
            # 钩子占位：暂未实现多轮/自适应检索，如实告知而不是假装支持。
            logger.info(
                "max_retrieval_iterations=%d 被请求，但当前版本暂未实现多轮检索，仍只跑 1 轮。",
                self.max_retrieval_iterations,
            )

        retriever = self._retriever if self._retriever is not None else _build_retriever()
        nodes = await retriever.aretrieve(QueryBundle(query_str=query_str))

        return RetrieveEvent(nodes=nodes, query_str=query_str, chat_history=chat_history, streaming=streaming)

    @step
    async def synthesize(self, ctx: Context, ev: RetrieveEvent) -> StopEvent:
        # --- 未来的工具选择钩子在这里 ---
        # 现在：检索到的 nodes 直接喂给 LLM 生成回答，没有"要不要调用工具"的
        # 决策。以后接入 MCP 工具后，这里可以换成 AgentWorkflow/FunctionAgent，
        # 让模型判断"这些 nodes 够不够回答，还是该先调用某个工具"。
        if not ev.nodes:
            if ev.streaming:
                ctx.write_event_to_stream(TokenEvent(token=_FALLBACK_ANSWER))
            return StopEvent(result=QAWorkflowResult(response=_FALLBACK_ANSWER, source_nodes=[]))

        context_str = "\n\n".join(node.get_content() for node in ev.nodes)
        prompt_str = Prompts.QA_PROMPT.value.format(context_str=context_str, query_str=ev.query_str)
        messages = [*ev.chat_history, ChatMessage(role=MessageRole.USER, content=prompt_str)]

        llm = self._llm if self._llm is not None else Settings.llm

        if ev.streaming:
            full_text_parts: list[str] = []
            stream = await llm.astream_chat(messages)
            async for chunk in stream:
                delta = chunk.delta or ""
                if delta:
                    full_text_parts.append(delta)
                    ctx.write_event_to_stream(TokenEvent(token=delta))
            answer_text = "".join(full_text_parts)
            if not answer_text.strip():
                # LLM 没吐出任何 token（比如空补全）：把兜底文案也当一个 token
                # 事件发出去，保证流式客户端至少收到点什么，而不是悄悄空着。
                answer_text = _FALLBACK_ANSWER
                ctx.write_event_to_stream(TokenEvent(token=answer_text))
        else:
            chat_response = await llm.achat(messages)
            answer_text = chat_response.message.content or ""
            if not answer_text.strip():
                answer_text = _FALLBACK_ANSWER

        return StopEvent(result=QAWorkflowResult(response=answer_text, source_nodes=ev.nodes))
