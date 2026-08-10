"""基于 llama_index.core.workflow 的问答工作流。

``router/graph.py`` 的 7 个既有端点（/create、/chat_stream、/query_stream、
/query_sources、/query、/agent、websocket /query）以及 /query_history、
/query_router 已经全部切到这里的 ``QAWorkflow`` 实现，不再走
``handlers/graph_builder.py`` 里原来的 ``CondenseQuestionChatEngine``/
``RouterQueryEngine`` 链路（那部分组装代码已删除，``graph_builder.py`` 只保留
``summary_index()``）。这里用 llama_index 官方推荐的 Workflow 原语（显式
``Event`` 在 step 之间传数据、``ctx.write_event_to_stream`` + 原生
``stream_events()`` 做流式）搭起同样的"检索 -> 生成"链路，Phase 3 阶段已经
验证过迁移可行、检索质量不低于原基线。

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

## 工具选择：另开路径，不塞进这个 workflow

``synthesize`` step 之前一直没有搭一个"模型自己决定要不要调用某个工具"的
Agent 决策循环——现在 ``agents/`` 包已经把工具选择做出来了（知识库检索/目录/
按来源取原文，见 ``agents/tools.py``），但**没有把它接进这个 workflow**，
而是在 ``agents/agent_workflow.py`` 里用独立的 ``FunctionAgent`` 编排、挂在
新端点 ``/graph/agent_chat``（不是这里、也不是被 ``/graph/agent`` 复用的
``QAWorkflow``）。原因是 QAWorkflow 是零额外决策开销的低延迟主路径（单轮
问答不多付一次 LLM 往返），而工具选择天然需要至少一次"要不要调用/调用
哪个"的决策 LLM 调用——把它硬塞进 ``synthesize`` 会让所有走这条 workflow
的请求都被迫多付这次延迟，即使绝大多数问题一次检索就够。两条路径并存，
低延迟和多跳能力都不用互相牺牲，详见 ``agents/agent_workflow.py`` 模块
docstring。

## rerank：挂钩，不重新实现

生产环境已经上线的条件触发式 rerank（``utils/rerank.py`` 的
``ConditionalRerankPostprocessor``，默认关闭，靠 ``load_env.RERANK_ENABLED``
开关）之前只挂在 ``graph_builder._build_query_engine()`` 的
``node_postprocessors=`` 参数上。``retrieve`` step 在拿到 ``retriever.
aretrieve()`` 的结果之后、构造 ``RetrieveEvent`` 之前，会再调用一次
``ConditionalRerankPostprocessor().postprocess_nodes(...)``——这是复用同一个
类，不是重新写一遍触发条件/阈值判断逻辑。该类内部已经处理好
``RERANK_ENABLED=False`` 时的直通截断（返回 ``nodes[:RERANK_TOP_N]``），
``retrieve`` step 这边不需要也不应该再判断一次开关。

## 条件触发查询改写：低置信度时先改写问题再检索一次

``retrieve`` step 在第一次检索后、rerank 前，检查 top1 分数是否低于
``load_env.QUERY_REWRITE_SCORE_THRESHOLD``（默认 0.6）。低于说明"检索结果
不自信"——常见场景是正确文档因为措辞/术语不匹配根本没进召回（评测里
q038/q069 的"标题关键词强匹配挤掉正确答案"就是这类），rerank 在已经召回的
内容里排序帮不上忙。这时用 ``Prompts.QUERY_REWRITE_PROMPT`` 让 LLM 把问题
改写得更适合检索（补同义词、全称、常见表述变体），拿改写后的查询再检索一次，
两次结果按 node_id 合并去重（改写结果在前）。

跟 rerank 的触发哲学一致：**只有低置信度才付出额外成本**。top1 >= 阈值时
零额外 LLM 调用、零第二次检索，保持单轮问答主路径的低延迟承诺；改写 LLM
调用失败时降级用原始查询（和 ``condense_question`` 压缩失败降级是同一个
模式），绝不因为改写这一步让请求挂掉。``RetrieveEvent.query_str`` 在改写
成功后携带改写后的查询（和 condense 后的问题同时驱动 retrieve/synthesize
是同一个逻辑），改写失败或未触发时保持原值。

这个功能默认开启（``QUERY_REWRITE_ENABLED=True``），阈值
``QUERY_REWRITE_SCORE_THRESHOLD``（默认 0.45）是拿真实评测数据校准过的：
campus-corpus 76 题里 top1 命中的分数范围 0.407~0.748、均值 0.546，阈值
设太高会把大部分正常查询拖进第二次检索。0.45 只对"检索确实没把握"的查询
触发（约 7%），高置信度查询零额外开销。注意分数阈值抓不住"分数不低但召回
了错误文档"的失败（比如 q038 的 0.55）——那是标题强匹配挤掉正确文档，需要
文档级去重或 metadata 过滤，不是查询改写能解决的，见 ``load_env.py`` 里同一
段注释。

## 多轮对话：加了问题压缩，跟 CondenseQuestionChatEngine 对齐

``retrieve`` step 之前现在有一个 ``condense_question`` step，复刻
``CondenseQuestionChatEngine`` 的"先把追问压缩成独立问题、再拿压缩后的问题
去检索"逻辑——用的是同一个 ``Prompts.CONDENSE_QUESTION_PROMPT``（见
``configs/config.py``），不是另写一套模板。压缩后的问题（``CondenseEvent.
query_str``）会同时用于检索和生成阶段的 prompt，这跟老链路里"压缩后的问题
既用于检索也用于 QA_PROMPT"的行为完全对齐，不是只压缩一半。

两个边界条件是刻意设计的：

- ``chat_history`` 为空（单轮问答，这是性能敏感的主路径）时，``condense_
  question`` step 完全不调用 LLM，直接把原始 ``query`` 透传成
  ``CondenseEvent.query_str``——不为压缩多付一次 LLM 往返的延迟。
- ``chat_history`` 非空但压缩这次 LLM 调用本身失败（网络抖动、超时等）时，
  不让异常网上传播炸穿整个 workflow——记一条 warning 日志，降级用原始
  ``query`` 顶上去。压缩是让追问检索更准的加分项，不是回答问题的必要条件，
  不能因为它挂了导致用户连兜底答案都拿不到。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

# DEFAULT_SIMILARITY_TOP_K 故意不在这里用 `from configs.load_env import X` 直接
# 绑定，理由见 handlers/graph_builder.py 顶部同样的说明——那样绑定会让
# reload_env_variables() 之后这个值就再也感知不到环境变量变化了。改成
# `import configs.load_env as load_env` + 使用处 `load_env.X` 属性访问，才能
# 在每次真正调用时读到最新值。
import configs.load_env as load_env
from configs.config import Prompts
from handlers.hybrid_retriever import build_retriever_for_index
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
from utils.rerank import ConditionalRerankPostprocessor

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIEVAL_ITERATIONS = 1
"""检索迭代上限的钩子。当前唯一实现的行为是跑 1 轮检索；这个参数为未来
multi-hop/自适应检索（第一轮结果不够时改写问题重新检索）预留，评测阶段的
经验建议这类迭代不超过 3 轮。见模块 docstring。"""

def safe_format(template: str, **kwargs) -> str:
    import string
    converted = re.sub(r'\{(\w+)\}', r'$\1', template)
    return string.Template(converted).safe_substitute(**kwargs)


_FALLBACK_ANSWER = "我还不知道，请反馈给我吧"
"""与现有 /query、websocket /query 端点里 Empty Response 的兜底文案保持一致。"""


class CondenseEvent(Event):
    """condense_question step 的输出：压缩（或原样透传）后的独立问题。

    ``query_str`` 在 ``chat_history`` 为空时就是原始 query；非空时是拿
    ``Prompts.CONDENSE_QUESTION_PROMPT`` 压缩过的独立问题（或压缩失败降级后
    的原始 query）。后续 ``retrieve``/``synthesize`` 两个 step 都只看这个
    字段，不再碰原始 query。见模块 docstring"多轮对话"一节。
    """

    query_str: str
    chat_history: list[ChatMessage] = Field(default_factory=list)
    streaming: bool = False


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


def resolve_effective_top_k(top_k: int | None) -> int:
    """``top_k`` 缺省值解析，从 ``_build_retriever`` 里抽出来单独复用。

    不传时，``RERANK_ENABLED`` 打开则用 ``load_env.RERANK_RECALL_K``、否则用
    ``load_env.DEFAULT_SIMILARITY_TOP_K``——这个分支不能省：``retrieve`` step
    里 ``ConditionalRerankPostprocessor`` 在 ``len(nodes) <= RERANK_TOP_N`` 时
    会直接跳过 rerank（候选数不够、没什么好排的），如果这里永远只取
    ``DEFAULT_SIMILARITY_TOP_K``（等于 ``RERANK_TOP_N``），rerank 就永远拿不到
    比 ``RERANK_TOP_N`` 更多的候选，条件触发形同虚设，等于 ``RERANK_ENABLED``
    打开也白打开。评测脚本 ``evals/run_workflow_retrieval_eval.py`` 需要按
    CLI 的 ``--top-k`` 显式覆盖——传参时优先用传入值，不套用这条 rerank
    相关的默认值逻辑。

    单独抽出来是因为 ``agents/tools.py`` 的知识库检索工具在指定了具体
    ``index_name``（走 ``build_retriever_for_index`` 单索引分支，不经过下面
    ``_build_retriever`` 的索引选择逻辑）时也需要同一套 top_k 缺省值解析——
    不这么做的话，Agent 工具这条路径的 rerank 条件触发会重蹈上面同一个坑，
    而且两处各写一份容易在改 rerank 参数时漏改一处。
    """
    if top_k is not None:
        return top_k
    return load_env.RERANK_RECALL_K if load_env.RERANK_ENABLED else load_env.DEFAULT_SIMILARITY_TOP_K


def _build_retriever(top_k: int | None = None) -> BaseRetriever:
    """复用 graph_builder._build_query_engine 的索引选择逻辑，只取 retriever。

    见模块 docstring"索引选择逻辑：复用，不重新发明"一节。``QAWorkflow`` 本身
    不新增 top_k 旋钮，`retrieve` step 仍然零参数调用 ``_build_retriever()``。
    """
    effective_top_k = resolve_effective_top_k(top_k)
    indexes_snapshot = list(indexes)
    if not indexes_snapshot:
        return _EmptyRetriever()
    if len(indexes_snapshot) == 1:
        return build_retriever_for_index(indexes_snapshot[0], effective_top_k)

    retriever_tools = [
        RetrieverTool.from_defaults(
            retriever=build_retriever_for_index(index, effective_top_k),
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
    """三步问答工作流：condense_question -> retrieve -> synthesize。

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
    async def condense_question(self, ctx: Context, ev: StartEvent) -> CondenseEvent:
        query_str: str = ev.query
        chat_history: list[ChatMessage] = list(getattr(ev, "chat_history", None) or [])
        streaming: bool = bool(getattr(ev, "streaming", False))

        if not chat_history:
            # 单轮问答主路径：零额外 LLM 调用，直接透传原始 query。见模块
            # docstring"多轮对话"一节。
            return CondenseEvent(query_str=query_str, chat_history=chat_history, streaming=streaming)

        history_str = "\n".join(f"{m.role.value}: {m.content}" for m in chat_history)
        prompt_str = safe_format(
            Prompts.CONDENSE_QUESTION_PROMPT.value.template,
            chat_history=history_str,
            question=query_str,
        )

        llm = self._llm if self._llm is not None else Settings.llm
        try:
            completion = await llm.acomplete(prompt_str)
            condensed = str(completion).strip()
            if not condensed:
                condensed = query_str
        except Exception:
            # 压缩是加分项，不是必需项：LLM 调用失败时降级用原始 query，
            # 不能让整个 workflow 因为压缩这一步挂掉。见模块 docstring。
            logger.warning("问题压缩（condense_question）调用 LLM 失败，降级使用原始 query。", exc_info=True)
            condensed = query_str

        return CondenseEvent(query_str=condensed, chat_history=chat_history, streaming=streaming)

    @step
    async def retrieve(self, ctx: Context, ev: CondenseEvent) -> RetrieveEvent:
        query_str: str = ev.query_str
        chat_history: list[ChatMessage] = ev.chat_history
        streaming: bool = ev.streaming

        if self.max_retrieval_iterations > 1:
            # 钩子占位：暂未实现多轮/自适应检索，如实告知而不是假装支持。
            logger.info(
                "max_retrieval_iterations=%d 被请求，但当前版本暂未实现多轮检索，仍只跑 1 轮。",
                self.max_retrieval_iterations,
            )

        retriever = self._retriever if self._retriever is not None else _build_retriever()
        nodes = await retriever.aretrieve(QueryBundle(query_str=query_str))
        # 条件触发查询改写：top1 置信度低时用 LLM 改写问题再检索一次。见模块
        # docstring"条件触发查询改写"一节。
        query_str, nodes = await self._maybe_rewrite_and_retrieve(retriever, query_str, nodes)
        # 生产环境的条件触发式 rerank 钩子：见模块 docstring"rerank：挂钩，不
        # 重新实现"一节。ConditionalRerankPostprocessor 内部已经处理好
        # RERANK_ENABLED=False 时的直通截断逻辑，这里不需要再判断一次开关。
        nodes = ConditionalRerankPostprocessor().postprocess_nodes(
            nodes, query_bundle=QueryBundle(query_str=query_str)
        )

        return RetrieveEvent(nodes=nodes, query_str=query_str, chat_history=chat_history, streaming=streaming)

    async def _maybe_rewrite_and_retrieve(
        self,
        retriever: BaseRetriever,
        query_str: str,
        nodes: list[NodeWithScore],
    ) -> tuple[str, list[NodeWithScore]]:
        """条件触发查询改写：top1 分数低于阈值时改写查询、再检索一次并合并。

        返回 (最终用于后续阶段的查询, 合并后的 nodes)。任何一步失败都降级为
        ``(query_str, nodes)`` 原样返回——改写是提升检索质量的加分项，不是回答
        问题的必要条件。见模块 docstring"条件触发查询改写"一节。
        """
        if not load_env.QUERY_REWRITE_ENABLED:
            return query_str, nodes
        if not nodes or nodes[0].score is None:
            return query_str, nodes
        if nodes[0].score >= load_env.QUERY_REWRITE_SCORE_THRESHOLD:
            return query_str, nodes

        llm = self._llm if self._llm is not None else Settings.llm
        prompt_str = safe_format(
            Prompts.QUERY_REWRITE_PROMPT.value.template,
            query_str=query_str,
        )
        try:
            completion = await llm.acomplete(prompt_str)
            rewritten = str(completion).strip()
        except Exception:
            logger.warning("查询改写（query rewrite）调用 LLM 失败，降级使用原始查询。", exc_info=True)
            return query_str, nodes

        if not rewritten or rewritten == query_str:
            return query_str, nodes

        logger.info("查询改写: %r -> %r（top1=%.3f < %.2f）",
                    query_str, rewritten, nodes[0].score, load_env.QUERY_REWRITE_SCORE_THRESHOLD)
        rewritten_nodes = await retriever.aretrieve(QueryBundle(query_str=rewritten))
        if not rewritten_nodes:
            return query_str, nodes

        # 合并去重：改写结果在前（它是针对"没检索对"这个诊断的修正），原始
        # 结果里没被改写结果覆盖的补在后面，避免丢失第一次检索独有的信息。
        seen_ids = {n.node.id_ for n in rewritten_nodes}
        merged = list(rewritten_nodes)
        for n in nodes:
            if n.node.id_ not in seen_ids:
                merged.append(n)
                seen_ids.add(n.node.id_)
        return rewritten, merged

    @step
    async def synthesize(self, ctx: Context, ev: RetrieveEvent) -> StopEvent:
        # 检索到的 nodes 直接喂给 LLM 生成回答，没有"要不要调用工具"的决策——
        # 这条低延迟主路径故意不做工具选择，需要多跳/工具选择的请求走
        # agents/agent_workflow.py 的独立 FunctionAgent 编排（/graph/agent_chat）。
        # 见模块 docstring"工具选择：另开路径，不塞进这个 workflow"一节。
        if not ev.nodes:
            if ev.streaming:
                ctx.write_event_to_stream(TokenEvent(token=_FALLBACK_ANSWER))
            return StopEvent(result=QAWorkflowResult(response=_FALLBACK_ANSWER, source_nodes=[]))

        context_str = "\n\n".join(node.get_content() for node in ev.nodes)
        prompt_str = safe_format(
            Prompts.QA_PROMPT.value.template,
            context_str=context_str,
            query_str=ev.query_str,
        )
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
