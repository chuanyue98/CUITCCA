"""自动路由：一次提问该走 QAWorkflow（standard）还是 FunctionAgent（agent）。

## 为什么要有这一层

聊天页原来有个"标准问答 / Agent 模式"切换器，把"这个问题复不复杂"的架构
决策甩给了用户——一个来问"图书馆几点开门"的学生根本没有依据判断该点哪个
按钮。两条链路（``handlers/qa_workflow.QAWorkflow`` 零决策开销的单次检索、
``agents/agent_workflow`` 可多跳的 ``FunctionAgent``）本身都没问题，问题是
选择权放错了地方——用户不该被要求理解后端架构才能问一句话。这里把选择权
收回后端：先按 standard 路径试着检索一次，检索置信度不够时才升级到 agent。

## 路由信号：为什么是"重排后的 top1 分数"，不是"融合(RRF)后的 top1 分数"

在 campus-corpus 真实语料上实测过两类问题的分数分布：

| | RRF 融合 top1 | 重排后 top1（cross-encoder） |
|---|---|---|
| 语料覆盖的问题 | 0.026-0.033 | 0.7286 / 0.9862 / 0.9863 |
| 语料未覆盖的问题 | 0.026-0.033 | 0.0097 / 0.0285 / 0.1565 / 0.4950 |

RRF 融合分数**没有任何区分度**——覆盖和未覆盖的问题落在完全相同的窄区间，
拿它去比任何阈值都等价于随机路由，绝对不能用。重排后的 cross-encoder 分数
区分度很好，``configs.load_env.AUTO_ROUTE_SCORE_THRESHOLD``（默认 0.6）取在
覆盖侧实测最低值 0.73 和未覆盖侧实测最高值 0.50 中间，两边都留了安全余量。
这组数据顺带发现了 ``utils/rerank.py`` 里一个既有问题（``Conditional
RerankPostprocessor`` 拿 RRF top1 去比 ``RERANK_SCORE_THRESHOLD``，导致"条件
触发"其实一直在无条件触发）——这次不修，只在那边补了如实记录的注释，见该
文件内的说明。

## 降级：RERANK_ENABLED 关闭时，只看"检索是否为空"

``ConditionalRerankPostprocessor`` 在 ``RERANK_ENABLED=False`` 时直通返回
（截断到 ``RERANK_TOP_N``，不做任何重排），这种情况下 nodes 上的分数还是
没有区分度的 RRF 融合分——上面那张表已经说明了这一点。如果这时仍然拿
``nodes[0].score`` 去跟 ``AUTO_ROUTE_SCORE_THRESHOLD`` 比较，比较的两个数字
一个有意义一个没意义，结果等价于随机路由，比不路由还糟（用户会看到"这题
明明很简单却随机地被甩给 Agent 多等好几秒"或者反过来）。所以 rerank 关闭
时这里只用"检索到内容 vs 检索为空"这一个信号：检索为空 -> agent（standard
反正给不出答案，不如让 agent 去试试换角度检索/查目录）；检索到内容 -> 直接
standard，不比分数阈值。

## 避免重复计算：问题压缩和检索都只做一次

路由判断本身就需要跑一次"压缩问题 + 检索 + 重排"，如果 standard 分支
又重新跑一遍会双倍检索延迟——所以 ``RouteDecision`` 把压缩后的
``query_str`` 和已经算好的 ``nodes`` 一起带出去，调用方（``router/graph.py``
的 ``/graph/ask_stream``）在 standard 分支把这两样东西直接喂给
``QAWorkflow``（通过注入一个只返回预先算好的 nodes 的占位 retriever，外加
``skip_condense=True`` 跳过二次压缩），不重复算一遍。

问题压缩复用的是 ``handlers.qa_workflow.condense_query()``——从
``QAWorkflow.condense_question`` step 里抽出来的同一份逻辑（同一个
prompt、同一套"历史为空零 LLM 调用""压缩失败降级用原 query"行为），不是
另写一套。

## agent 分支为什么不传压缩后的问题

路由到 agent 时，调用方传给 ``run_agent``/``stream_agent_events`` 的是
**原始** query，不是这里算出来的压缩版 ``query_str``。压缩 prompt
（``CONDENSE_QUESTION_PROMPT``）是为"生成一个适合检索的独立问题"调的，
``FunctionAgent`` 本来就会拿到完整 ``chat_history`` 自己理解上下文，再喂一个
已经被压缩改写过的版本反而可能丢失语气/追问细节，对多跳决策没有增益。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

import configs.load_env as load_env
from handlers.qa_workflow import _build_retriever, condense_query
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.llms import LLM
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.settings import Settings
from utils.rerank import ConditionalRerankPostprocessor

logger = logging.getLogger(__name__)

MODE_STANDARD = "standard"
MODE_AGENT = "agent"

FOLLOWUP_SUGGESTION_MAX_COUNT = 3
"""追问建议条数上限。用户反馈"提问本身就费劲"，2-3 条够给用户一个"往下点"
的抓手，太多反而增加选择负担，也拉长生成 prompt/解析成本。"""

FOLLOWUP_SUGGESTION_TIMEOUT_SECONDS = 8.0
"""追问建议生成的超时上限。这次 LLM 调用被刻意放在答案已经流式吐完之后才
发起（见 ``generate_followup_suggestions`` docstring），不能反过来拖慢或
卡住主回答，所以给一个比较紧的超时——超时同样走"静默返回空数组"的降级
路径，不重试、不阻塞。"""


@dataclass
class RouteDecision:
    """一次路由判定的结果。

    ``nodes``/``query_str`` 是路由判定过程中已经算出来的中间结果，调用方
    (standard 分支) 直接复用，不要重新检索/重新压缩——见模块 docstring
    "避免重复计算"一节。``reason`` 是给前端/日志展示的人类可读说明，不是
    给下游逻辑分支用的（分支逻辑应该看 ``mode``）。
    """

    mode: str
    nodes: list[NodeWithScore] = field(default_factory=list)
    query_str: str = ""
    reason: str = ""


async def route_query(
    query: str,
    *,
    chat_history: list[ChatMessage] | None = None,
    retriever: BaseRetriever | None = None,
    llm: LLM | None = None,
    top_k: int | None = None,
) -> RouteDecision:
    """决定这次提问走 standard 还是 agent，顺带返回已经算好的中间结果。

    ``retriever``/``llm`` 可以显式注入（测试用，避免碰真实索引/真实模型），
    不传则分别用 ``handlers.qa_workflow._build_retriever()`` 和
    ``Settings.llm``——跟 ``QAWorkflow.__init__`` 的注入模式一致。
    """
    chat_history = list(chat_history or [])

    # 问题压缩：复用 QAWorkflow 用的同一个函数，不另写一套 prompt 拼接逻辑。
    # chat_history 为空时函数内部直接透传，连 Settings.llm 都不会解析——这里
    # 故意不提前 resolve llm，把"要不要碰 Settings.llm"完全交给
    # condense_query 自己判断，见该函数 docstring。
    query_str = await condense_query(query, chat_history, llm)

    active_retriever = retriever if retriever is not None else _build_retriever(top_k)
    try:
        nodes = await active_retriever.aretrieve(QueryBundle(query_str=query_str))
    except Exception:
        # 检索失败：standard 分支反正给不出答案（QAWorkflow 的 retrieve step
        # 遇到这种情况也是降级成空 nodes 走兜底文案），不如交给 agent 试试
        # 换个角度检索或者先看看目录，agent 的工具调用有自己的错误处理。
        logger.warning("auto_router 首次检索失败，降级路由到 agent。", exc_info=True)
        return RouteDecision(
            mode=MODE_AGENT, nodes=[], query_str=query_str, reason="检索失败，交给 Agent 深入查证"
        )

    if not nodes:
        return RouteDecision(
            mode=MODE_AGENT, nodes=[], query_str=query_str, reason="知识库未直接检索到相关内容，交给 Agent 深入查证"
        )

    # 复用生产环境已有的条件触发式 rerank，不重新实现触发条件/阈值判断。
    nodes = ConditionalRerankPostprocessor().postprocess_nodes(
        nodes, query_bundle=QueryBundle(query_str=query_str)
    )

    if not load_env.RERANK_ENABLED:
        # rerank 关闭时 nodes[0].score 是没有区分度的 RRF 融合分，不能拿它
        # 跟 AUTO_ROUTE_SCORE_THRESHOLD 比——见模块 docstring"降级"一节。
        # 只用"检索到内容"这一个信号，命中就直接走 standard。
        return RouteDecision(
            mode=MODE_STANDARD,
            nodes=nodes,
            query_str=query_str,
            reason="已检索到相关内容（rerank 未开启，仅按是否命中路由）",
        )

    top1_score = nodes[0].score if nodes[0].score is not None else 0.0
    if top1_score < load_env.AUTO_ROUTE_SCORE_THRESHOLD:
        return RouteDecision(
            mode=MODE_AGENT,
            nodes=nodes,
            query_str=query_str,
            reason=f"检索置信度不足（top1={top1_score:.2f} < {load_env.AUTO_ROUTE_SCORE_THRESHOLD:.2f}），"
            f"交给 Agent 深入查证",
        )

    return RouteDecision(
        mode=MODE_STANDARD,
        nodes=nodes,
        query_str=query_str,
        reason=f"已检索到高置信度内容（top1={top1_score:.2f}）",
    )


async def generate_followup_suggestions(
    query_str: str,
    nodes: list[NodeWithScore],
    *,
    llm: LLM | None = None,
) -> list[str]:
    """基于这一轮的问题 + 检索到的内容，生成 2-3 条追问建议。

    用户反馈"提问本身就费劲"——很多学生不知道知识库里到底覆盖了什么、该往
    哪个方向追问。这里不凭空让 LLM 自由发挥，而是把**这一轮已经检索到的
    nodes 原文**喂给它出题，要求生成的追问必须能从这些资料里找到答案——
    保证建议是"知识库真的答得上来的"，不是听起来合理但一问就"我还不知道"
    的假追问。

    调用方（``router/graph.py`` 的 ``/graph/ask_stream``）必须在主回答**流式
    输出完成之后**才调用这个函数——这是一次额外的小 LLM 调用，绝不能挤占
    或延迟用户看到答案的时间。

    失败/超时都静默降级返回空列表，不向上抛异常：追问建议是锦上添花的
    体验优化，不是回答问题的必要条件，这个函数本身不应该有任何路径能让
    调用方的主流程被拖垮。
    """
    if not nodes:
        return []

    resolved_llm = llm if llm is not None else Settings.llm
    # 只取前几个 node 的原文，不是全部塞进去：追问建议只需要"这一轮聊到了
    # 什么话题"的大致范围，不需要把检索到的全部上下文（可能远超 QA 阶段的
    # RERANK_TOP_N）都喂进去多花 token/延迟。
    context_str = "\n\n".join(node.get_content() for node in nodes[:FOLLOWUP_SUGGESTION_MAX_COUNT * 2])
    prompt = (
        "你是成都信息工程大学校园小助手。基于下面这轮问答用到的资料，生成"
        f"2 到 {FOLLOWUP_SUGGESTION_MAX_COUNT} 条用户接下来可能想追问的问题，"
        "帮用户在不知道怎么问的时候有得点。\n"
        "严格要求：\n"
        "1. 每条追问必须能从下面提供的资料内容里直接找到答案，禁止凭空发散、"
        "禁止问资料没有涉及的内容。\n"
        "2. 每条追问是一句可以直接发送的完整问题，不是关键词或短语。\n"
        "3. 不要与用户刚问过的问题重复或换个说法重复。\n"
        "4. 只输出一个 JSON 字符串数组，不要任何解释、不要 markdown 代码块标记。\n"
        f"<本轮问题>\n{query_str}\n"
        f"<可用资料>\n{context_str}\n"
        "<JSON 数组>"
    )

    try:
        completion = await asyncio.wait_for(
            resolved_llm.acomplete(prompt), timeout=FOLLOWUP_SUGGESTION_TIMEOUT_SECONDS
        )
        raw = str(completion).strip()
    except Exception:
        # TimeoutError 也在这里被捕获：asyncio.TimeoutError 是 Exception 的
        # 子类，跟"LLM 调用本身失败"走同一条降级路径，不需要单独 except 分支。
        logger.warning("追问建议生成调用 LLM 失败或超时，降级返回空列表。", exc_info=True)
        return []

    return _parse_suggestion_list(raw)[:FOLLOWUP_SUGGESTION_MAX_COUNT]


def _parse_suggestion_list(raw: str) -> list[str]:
    """解析 LLM 输出的 JSON 字符串数组，解析失败/格式不对一律返回空列表。

    LLM 偶尔会不听话地包一层 ```json ... ``` 代码块，先剥掉再解析；不是
    合法 JSON、或者解析出来不是"字符串数组"，都当作生成失败处理——宁可
    没有建议，也不能把半成品/非字符串内容展示给用户。
    """
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
