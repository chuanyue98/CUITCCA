"""Agent 可调用的工具实现 + 默认工具集的注册。

## 只做这个项目真实具备的能力

三个"必须有"的工具都是把已经在生产上跑的检索链路包一层"给 LLM 用的接口"，
没有新造任何检索/存储能力：

- ``search_knowledge_base``：走 ``handlers.hybrid_retriever.
  build_retriever_for_index``（BM25+dense RRF 融合，带缓存）+
  ``utils.rerank.ConditionalRerankPostprocessor``（条件触发 rerank）——跟
  ``handlers/qa_workflow.py`` 的 ``retrieve`` step 是同一条链路，只是这里
  多索引场景用同一个 ``_build_retriever()``（见下面的说明）。
- ``list_knowledge_bases``：读 ``handlers.index_crud.indexes`` 这个模块级
  列表，就是现在系统里已加载的索引，没有额外查询。
- ``get_document_chunks_by_source``：直接查 Chroma collection 的
  ``metadata`` 字段（``file_name``/``source_url``），复用
  ``handlers.vector_store._get_client()``——跟 ``handlers/index_crud.py``
  里 ``get_all_docs``/``deleteDocById`` 用的是同一个客户端和同一种
  ``collection.get(where=...)`` 调用方式，不是另起一条访问 Chroma 的路子。

日期工具 ``get_current_datetime`` 只做纯本地时间计算，语料里没有 2026 年
校历数据，工具描述里明确写清楚它不知道学校的具体安排——不装作能查校历。

## 索引选择：单索引场景复用 build_retriever_for_index，多索引场景复用
   qa_workflow 的路由分支，不重新发明

``search_knowledge_base`` 传了 ``index_name`` 时，直接
``build_retriever_for_index(index, top_k)``——调用方（LLM）已经明确指定了
索引，不需要也不应该再走一次 selector 决策。没传 ``index_name`` 时调用
``handlers.qa_workflow._build_retriever()``，复用它已经测试过的 0/1/多个
索引三分支（多个索引时用 ``RouterRetriever`` + ``LLMSingleSelector``）——
这跟 ``QAWorkflow`` 自己不指定索引时的行为完全一致，两处用同一份索引选择
逻辑，不会出现"Agent 工具和 QAWorkflow 对同一个问题选了不同索引"这种
不一致。

## 返回结构化 JSON 字符串，不是纯文本

每个工具函数返回值都是 ``json.dumps(...)`` 出来的字符串，不是拼好的自然语言
段落。原因：
1. ``FunctionTool`` 会把返回值原样喂给 LLM 当"工具执行结果"——JSON 结构
   化文本对 LLM 解析源信息（node_id/file_name/source_url/score）比自由格式
   段落更可靠，模型更容易在最终回答里正确带上"信息来自哪个文档"。
2. 调用方（``agents/agent_workflow.py`` 的 ``ToolCallResult.tool_output.
   raw_output``）拿到的也是这同一个 JSON 字符串，可以直接 ``json.loads``
   解析出结构化的来源列表用于前端展示/引用溯源，不需要用正则从一段自然语言
   里抠 file_name。
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.registry import ToolRegistry, ToolSpec
from handlers.hybrid_retriever import build_retriever_for_index
from handlers.index_crud import get_index_by_name, indexes
from llama_index.core.schema import NodeWithScore, QueryBundle
from utils.llama import index_description
from utils.rerank import ConditionalRerankPostprocessor

logger = logging.getLogger(__name__)

# 单条检索结果/取原文片段最多带给 LLM 的原文字符数——防止一次工具调用把
# 大段原文塞进 LLM 上下文，挤爆后面还要用的检索/生成预算。跟人读一屏内容
# 差不多的量级，够 LLM 判断相关性和引用，不是要把整篇文档喂过去。
_MAX_SNIPPET_CHARS = 800

# get_document_chunks_by_source 的片段数上限——同样是为了不让一次工具调用
# 占满上下文；5 是默认值（一次追问通常不需要更多），20 是硬上限。
_DEFAULT_MAX_CHUNKS = 5
_HARD_MAX_CHUNKS = 20

# 成都信息工程大学所在时区，get_current_datetime 用这个而不是服务器本地时区
# ——生产环境跑在哪个时区不一定，但面向的用户固定在成都。
_CAMPUS_TZ = ZoneInfo("Asia/Shanghai")

_WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def _truncate(text: str, limit: int = _MAX_SNIPPET_CHARS) -> tuple[str, bool]:
    text = text or ""
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _node_to_source_dict(node_with_score: NodeWithScore) -> dict:
    node = node_with_score.node
    metadata = node.metadata or {}
    text, truncated = _truncate(node.get_content())
    return {
        "node_id": node.id_,
        # 必须显式转成 Python float：重排器（SentenceTransformerRerank）是直接
        # `node.score = <numpy 值>` 赋值的，而 Pydantic v2 默认**不校验赋值**，
        # 所以 numpy.float32 会原样留在 score 上，后面 json.dumps 直接抛
        # "Object of type float32 is not JSON serializable"，整个工具调用返回
        # is_error=True。
        #
        # 这条路径几乎必然被踩到：只要召回数多于 RERANK_TOP_N，重排就会执行
        # （见 utils/rerank.py 里关于"条件触发实际上恒为真"的说明），也就是说
        # Agent 的知识库检索工具在真实查询下基本每次都会失败。
        "score": float(node_with_score.score) if node_with_score.score is not None else None,
        "file_name": metadata.get("file_name"),
        "source_url": metadata.get("source_url"),
        "text": text,
        "truncated": truncated,
    }


async def search_knowledge_base(query: str, index_name: str | None = None, top_k: int | None = None) -> str:
    query = (query or "").strip()
    if not query:
        return json.dumps({"error": "query 不能为空，请提供具体要检索的问题或关键词。"}, ensure_ascii=False)

    # 延迟 import：避免 agents 包在模块加载期就跟 handlers.qa_workflow 产生
    # 强制的导入时依赖（qa_workflow 反过来不 import agents，本来就没有环形
    # 依赖，这里延迟只是保持跟本文件其它函数一致的风格，方便测试里按需 patch）。
    from handlers.qa_workflow import _build_retriever, resolve_effective_top_k

    try:
        if index_name:
            index = get_index_by_name(index_name)
            if index is None:
                available = [idx.index_id for idx in indexes]
                return json.dumps(
                    {
                        "error": f"未找到名为 {index_name!r} 的知识库索引。",
                        "available_indexes": available,
                    },
                    ensure_ascii=False,
                )
            retriever = build_retriever_for_index(index, resolve_effective_top_k(top_k))
        else:
            # 不指定索引：复用 QAWorkflow 同一套 0/1/多索引选择逻辑，见模块
            # docstring。
            retriever = _build_retriever(top_k=top_k)

        query_bundle = QueryBundle(query_str=query)
        nodes = await retriever.aretrieve(query_bundle)
        nodes = ConditionalRerankPostprocessor().postprocess_nodes(nodes, query_bundle=query_bundle)
    except Exception:
        logger.exception("search_knowledge_base 检索失败: query=%r index_name=%r", query, index_name)
        return json.dumps(
            {"error": "检索时出现内部错误，这不代表知识库里没有相关内容，可以换个说法重试一次。"},
            ensure_ascii=False,
        )

    results = [_node_to_source_dict(n) for n in nodes]
    return json.dumps({"query": query, "index_name": index_name, "result_count": len(results), "results": results},
                       ensure_ascii=False)


async def list_knowledge_bases() -> str:
    payload = [{"index_name": idx.index_id, "summary": index_description(idx)} for idx in list(indexes)]
    return json.dumps({"index_count": len(payload), "indexes": payload}, ensure_ascii=False)


def _collect_chunks_from_collection(collection, source: str, remaining: int) -> list[dict]:
    """在一个 Chroma collection 里按 file_name/source_url 两个 metadata 字段
    分别查一次再合并去重，而不是拼一个 ``$or`` 查询——两次简单查询在所有
    chromadb 版本上都能跑，不用去赌当前锁定版本对复合查询语法的支持程度。"""
    seen_ids: set[str] = set()
    chunks: list[dict] = []
    for key in ("file_name", "source_url"):
        if len(chunks) >= remaining:
            break
        try:
            data = collection.get(where={key: source}, limit=remaining)
        except Exception:
            logger.exception("查询 Chroma collection 按 %s=%r 失败", key, source)
            continue
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metadatas = data.get("metadatas") or []
        for node_id, text, metadata in zip(ids, docs, metadatas, strict=False):
            if node_id in seen_ids or len(chunks) >= remaining:
                continue
            seen_ids.add(node_id)
            snippet, truncated = _truncate(text or "")
            chunks.append({
                "node_id": node_id,
                "file_name": (metadata or {}).get("file_name"),
                "source_url": (metadata or {}).get("source_url"),
                "text": snippet,
                "truncated": truncated,
            })
    return chunks


def _get_document_chunks_by_source_sync(source: str, index_name: str | None, max_chunks: int) -> str:
    from handlers.vector_store import _get_client

    if index_name:
        target_index = get_index_by_name(index_name)
        if target_index is None:
            available = [idx.index_id for idx in indexes]
            return json.dumps(
                {"error": f"未找到名为 {index_name!r} 的知识库索引。", "available_indexes": available},
                ensure_ascii=False,
            )
        target_indexes = [target_index]
    else:
        target_indexes = list(indexes)

    client = _get_client()
    chunks: list[dict] = []
    for idx in target_indexes:
        if len(chunks) >= max_chunks:
            break
        try:
            collection = client.get_collection(idx.index_id)
        except Exception:
            logger.exception("获取 Chroma collection 失败: index_id=%r", idx.index_id)
            continue
        found = _collect_chunks_from_collection(collection, source, max_chunks - len(chunks))
        for chunk in found:
            chunk["index_name"] = idx.index_id
        chunks.extend(found)

    return json.dumps({"source": source, "chunk_count": len(chunks), "chunks": chunks}, ensure_ascii=False)


async def get_document_chunks_by_source(source: str, index_name: str | None = None, max_chunks: int = 5) -> str:
    source = (source or "").strip()
    if not source:
        return json.dumps(
            {"error": "source 不能为空，请提供从检索结果里拿到的 file_name 或 source_url。"},
            ensure_ascii=False,
        )
    max_chunks = max(1, min(max_chunks or _DEFAULT_MAX_CHUNKS, _HARD_MAX_CHUNKS))

    try:
        # chromadb 的 collection.get() 是阻塞 I/O（本地磁盘），扔到线程池里跑，
        # 不占用 FunctionAgent 所在的事件循环——跟 handlers/index_crud.py
        # _ingest_and_persist 用 asyncio.to_thread 卸载摄取工作是同一个理由。
        return await asyncio.to_thread(_get_document_chunks_by_source_sync, source, index_name, max_chunks)
    except Exception:
        logger.exception("get_document_chunks_by_source 失败: source=%r index_name=%r", source, index_name)
        return json.dumps({"error": "查询原文片段时出现内部错误，可以稍后重试。"}, ensure_ascii=False)


def get_current_datetime() -> str:
    now = datetime.now(_CAMPUS_TZ)
    _, iso_week, iso_weekday = now.isocalendar()
    return json.dumps(
        {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": _WEEKDAY_CN[iso_weekday - 1],
            "iso_week": iso_week,
            "note": (
                "这只是当前自然日期/时间的计算结果，不了解成都信息工程大学的校历"
                "（开学时间、教学周对应关系、放假安排等）。不要用这个结果推断"
                "\"现在是开学第几周\"之类需要校历数据支撑的问题——知识库里没有这类"
                "数据，查不到就如实说不知道，不要用日期拼一个答案出来。"
            ),
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 默认工具集注册。工具描述是模型选择工具的唯一依据，见模块 docstring；每条都
# 写清楚"什么时候该用/不该用、参数什么意思、返回什么形状"。
# ---------------------------------------------------------------------------

SEARCH_KNOWLEDGE_BASE = "search_knowledge_base"
LIST_KNOWLEDGE_BASES = "list_knowledge_bases"
GET_DOCUMENT_CHUNKS_BY_SOURCE = "get_document_chunks_by_source"
GET_CURRENT_DATETIME = "get_current_datetime"


def register_default_tools(registry: ToolRegistry) -> None:
    """把项目当前真实具备的工具能力灌进一个 ``ToolRegistry``。

    调用方（``agents/agent_workflow.py`` 的 ``get_default_registry()``，或
    测试里想要一份干净注册表的场景）负责创建 ``ToolRegistry()`` 实例，这个
    函数只管注册，不管实例的生命周期——保持"注册表容器"和"工具实现"两件事
    解耦，见 ``registry.py`` 模块 docstring。
    """
    registry.register(
        ToolSpec(
            name=SEARCH_KNOWLEDGE_BASE,
            description=(
                "在校园知识库中做语义+关键词混合检索，返回若干条候选内容及其来源标识"
                "（node_id、file_name/source_url、score）。这是回答具体事实类问题"
                "（\"XX是什么/怎么样/在哪里/流程是什么\"）时应该优先调用的工具——不要"
                "凭已有知识直接回答校园相关问题，先查一次。\n"
                "参数：query 是你想查的问题或关键词，用中文自然语言即可；index_name"
                "可选，不传时会在所有已加载的知识库里按同一套路由逻辑自动选择最相关"
                "的索引，如果你已经用「列出知识库」确认过某个具体索引更合适，可以"
                "显式传它的 index_name 来精确检索；top_k 可选，控制返回候选条数，"
                "不传则用系统默认值，不确定就不要传。\n"
                "如果第一次检索结果不相关或数量不足，可以换一个更具体/换个角度的"
                "query 再调用一次本工具，而不是直接放弃——但不要在同一个问题上无"
                "意义地反复调用。\n"
                "返回 JSON 字符串，包含 results 列表，每条有 node_id/score/"
                "file_name/source_url/text。回答时必须基于这些 text 内容，并尽量"
                "指出信息来自哪个 file_name 或 source_url 方便用户核实。results 为"
                "空表示没查到任何相关内容，这种情况不要编造答案。"
            ),
            async_fn=search_knowledge_base,
        )
    )
    registry.register(
        ToolSpec(
            name=LIST_KNOWLEDGE_BASES,
            description=(
                "列出当前系统里已经加载的所有知识库索引及其摘要（每个索引对应一批"
                "已入库的校园文档）。在不确定该往哪个知识库里检索、或者想先了解"
                "\"现在有哪些资料\"时，可以先调用这个工具看一眼，再决定调用「知识库"
                "检索」时要不要指定 index_name。这个工具不做任何检索、不需要任何"
                "参数，开销很小，可以放心先调用；但如果已经明确知道要查什么内容，"
                "不必每次都先调用它——直接检索也可以。\n"
                "返回 JSON，包含 indexes 列表，每条有 index_name 和 summary。"
            ),
            async_fn=list_knowledge_bases,
        )
    )
    registry.register(
        ToolSpec(
            name=GET_DOCUMENT_CHUNKS_BY_SOURCE,
            description=(
                "给定一个具体的文件名（file_name）或来源链接（source_url，二者选一"
                "即可），取回该文档在知识库里的若干原始片段（chunk）。这个来源"
                "标识通常来自「知识库检索」工具返回结果里的 file_name/source_url"
                "字段——用于核实某条检索结果的上下文，或者用户追问\"这份文档里还"
                "说了什么\"之类需要看更多原文的场景。\n"
                "不要在还没有任何检索结果、不知道具体文件名/链接的情况下调用它"
                "——那种情况应该先调用「知识库检索」拿到来源标识。\n"
                "参数：source 是文件名或链接；max_chunks 控制最多取回几个片段"
                "（默认 5，上限 20）；index_name 可选，不传时会在所有知识库里查找。\n"
                "返回 JSON，chunks 为空表示没有找到匹配这个来源的内容。"
            ),
            async_fn=get_document_chunks_by_source,
        )
    )
    registry.register(
        ToolSpec(
            name=GET_CURRENT_DATETIME,
            description=(
                "返回当前的公历日期、时间和 ISO 周数，纯本地计算，不查询任何数据源。"
                "仅在用户问题明确需要\"今天几号/现在几点/这是今年第几周\"这类当前"
                "时间信息时才调用，不要为了猜校历安排去调用它。\n"
                "重要限制：这个工具完全不知道成都信息工程大学的校历安排（开学时间、"
                "教学周对应关系、放假安排等），不要用它的返回结果推断\"现在是开学第"
                "几周\"之类需要校历数据支撑的问题——知识库里没有这类数据，如果被问"
                "到这类问题且检索不到相关内容，应如实说不知道，而不是拿日期编一个"
                "答案。"
            ),
            fn=get_current_datetime,
        )
    )


_default_registry: ToolRegistry | None = None


def build_default_registry() -> ToolRegistry:
    """构造一份全新的、注册了全部默认工具的 ``ToolRegistry``。

    每次调用都是新实例——测试想要一份不受其它测试污染（比如某个测试
    disable 了某个工具）的干净注册表时用这个，不要用下面的
    ``get_default_registry()``。
    """
    registry = ToolRegistry()
    register_default_tools(registry)
    return registry


def get_default_registry() -> ToolRegistry:
    """生产路径用的单例注册表，懒加载、进程内复用。

    工具构造本身很轻（没有 I/O，只是把函数包成 ``ToolSpec``），单例主要是
    避免每个请求都重新跑一遍注册流程；真正的检索/查询开销都在工具被
    **调用**的时候才发生，跟这个单例是否存在无关。
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = build_default_registry()
    return _default_registry
