"""语义缓存 + 人工问答沉淀（handlers/qa_cache.py）。

## 解决什么问题

学生高频问题（\"图书馆几点开门\"）每次都走完整的\"压缩 -> 检索 -> 重排 -> LLM
生成\"链路，同样的问答重复花检索时间和 LLM token。生产级 RAG 平台的标配能力
（Dify 的 annotation reply、各类 semantic cache）就是\"同问同答不重算\"，这里
补上：**相同/相似问题直接复用历史答案**，跳过检索与生成，命中的响应延迟从
秒级降到毫秒级（本地 bge-m3 嵌入一次）。

## 两种 kind，两种命中策略

- ``auto``：每次成功的问答自动写入（``store_auto``）。答案**未经人工校验**，
  命中阈值 ``QA_CACHE_AUTO_THRESHOLD``（0.92，几乎逐字相同）才敢直接复用——
  宁可 miss 多花一次检索，也不能拿自动条目的答案去应付一个意思不同的新问题。
- ``curated``：用户在答案下点 👍（``/graph/qa_feedback``，``store_curated``）
  人工背书的高价值问答——Dify annotation reply 同款机制。阈值
  ``QA_CACHE_CURATED_THRESHOLD``（0.82，允许一定程度的同义改写）更宽：人确认
  过的答案，措辞不同但意思一样就该命中。

## 存储与容量

独立 Chroma collection（``QA_CACHE_COLLECTION``，创建时指定 cosine 距离空间，
见 ``handlers/vector_store.get_or_create_collection`` 的 metadata 参数），
document 存问题原文（被嵌入），答案/来源/命中次数存 metadata。``hits`` 记录
命中次数：auto 条目超过 ``QA_CACHE_MAX_AUTO_ENTRIES`` 时按命中次数升序驱逐最
不常用的（容量控制只针对无人背书的自动条目）；curated 是人工资产，永不自动
驱逐。

## 设计约束：缓存是 best-effort 的

查找/写入/删除/统计的每一步都可能因为 Chroma 不可用、嵌入模型未配置等原因
失败，所有对外函数都保证**不向调用方抛异常**——缓存命中是省成本的加分项，
不是回答问题的必要条件，任何一条失败路径都只能静默降级成\"没缓存\"，不能
拖垮主问答流程（跟 utils/rerank.py、handlers/auto_router.py 的降级哲学一致）。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass

import configs.load_env as load_env
from llama_index.core.schema import NodeWithScore
from llama_index.core.settings import Settings

logger = logging.getLogger(__name__)

KIND_AUTO = "auto"
KIND_CURATED = "curated"

# Chroma 单条 metadata 有 ~40KB 上限，答案/来源片段按此截断存储。缓存是
# best-effort 优化，截断超长答案换取不越界；正常 LLM 回答远小于这个长度。
_ANSWER_MAX_CHARS = 8000
_SOURCE_TEXT_MAX_CHARS = 300

# 缓存查找的 I/O 超时。"best-effort"承诺的是不抛异常，但一个挂起的 Chroma 调用
# 会拖住主问答流（lookup 在路由判定之前执行，就在关键路径上）——跟追问建议
# 生成有 8 秒超时同理，这里给 2 秒，超时按未命中降级。
_LOOKUP_TIMEOUT_SECONDS = 2.0


@dataclass
class CachedEntry:
    """一次缓存命中拿到的内容。"""

    kind: str
    answer: str
    source_file: str = ""
    source_text: str = ""


def _get_collection():
    from handlers.vector_store import get_or_create_collection

    collection = get_or_create_collection(
        load_env.QA_CACHE_COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    # 距离空间只在**新建** collection 时生效（Chroma 对已存在的集合忽略创建
    # 参数）。如果 qa_cache 曾经以默认 L2 空间创建过，这里的
    # similarity = 1 - distance 换算就失真了（L2 距离可以超过 1），阈值判断
    # 会静默失效——与其悄悄算错，不如每次启动告警一次，让人能发现。
    space = (collection.metadata or {}).get("hnsw:space")
    if space != "cosine":
        logger.warning(
            "qa_cache collection 的距离空间是 %r 而不是 cosine，语义缓存相似度阈值判断可能失真。",
            space,
        )
    return collection


async def _embed(text: str) -> list[float]:
    """问题 -> 向量，用跟检索链路同一个全局嵌入模型（bge-m3）。"""
    return await Settings.embed_model.aget_query_embedding(text)


def _entry_id(kind: str, question: str) -> str:
    # 稳定 id：同 kind + 同问题重复写入时 upsert 覆盖旧条目（最新答案生效），
    # 不会在 collection 里积累重复问题。
    # usedforsecurity=False：非安全用途的去重指纹（bandit B324），且指纹
    # 算法不能换——换了会让 Chroma 里既有缓存条目的 id 全部对不上。
    return f"{kind}:{hashlib.sha1(question.encode('utf-8'), usedforsecurity=False).hexdigest()}"


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + "…"


def _first_source(sn: NodeWithScore) -> tuple[str, str]:
    """取来源节点的 file_name + 文本片段（缓存命中时让引用来源仍可显示）。"""
    file_name = (sn.node.metadata or {}).get("file_name")
    if not isinstance(file_name, str):
        file_name = ""
    return file_name, sn.node.get_content()


async def lookup(query: str) -> CachedEntry | None:
    """查语义缓存：命中返回条目，未命中返回 None；任何失败都降级为 None。"""
    if not load_env.QA_CACHE_ENABLED:
        return None
    query = query.strip()
    if not query:
        return None
    try:
        embedding = await _embed(query)
        collection = _get_collection()
        # Chroma 的 query/update 是同步阻塞调用：包 to_thread + wait_for，一个
        # 挂起的本地 sqlite 也不会拖住事件循环和整条问答流（见模块级
        # _LOOKUP_TIMEOUT_SECONDS 注释）。
        result = await asyncio.wait_for(
            asyncio.to_thread(
                collection.query,
                query_embeddings=[embedding],
                n_results=1,
                include=["metadatas", "distances"],
            ),
            timeout=_LOOKUP_TIMEOUT_SECONDS,
        )
    except Exception:
        # TimeoutError 也是 Exception 子类，超时走同一条降级路径
        logger.warning("语义缓存查找失败或超时，降级为未命中。", exc_info=True)
        return None

    ids = result.get("ids") or [[]]
    if not ids or not ids[0]:
        return None
    entry_id = ids[0][0]
    metadata = (result.get("metadatas") or [[{}]])[0][0]
    # cosine 空间下 distance = 1 - cosine_similarity，阈值判断换算回相似度。
    distance = (result.get("distances") or [[1.0]])[0][0]
    similarity = 1.0 - float(distance)
    kind = metadata.get("kind", KIND_AUTO)
    threshold = (
        load_env.QA_CACHE_CURATED_THRESHOLD
        if kind == KIND_CURATED
        else load_env.QA_CACHE_AUTO_THRESHOLD
    )
    if similarity < threshold:
        return None

    # 命中计数（驱逐排序用）。best-effort：更新失败不影响本次命中。
    # 并发下是读-改-写，可能丢更新——hits 只是驱逐排序的启发式信号，不是
    # 精确计数，丢一两次不影响正确性，刻意不做原子化。
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                collection.update,
                ids=[entry_id],
                metadatas=[{"hits": int(metadata.get("hits", 0)) + 1}],
            ),
            timeout=_LOOKUP_TIMEOUT_SECONDS,
        )
    except Exception:
        pass

    return CachedEntry(
        kind=kind,
        answer=metadata.get("answer", "") or "",
        source_file=metadata.get("source_file", "") or "",
        source_text=metadata.get("source_text", "") or "",
    )


async def _store(
    query: str,
    answer: str,
    source_nodes: list[NodeWithScore],
    kind: str,
) -> None:
    if not load_env.QA_CACHE_ENABLED:
        return
    query = query.strip()
    if not query or not answer.strip():
        # 空问题 / 空答案不缓存（出错降级的兜底文案也不该进缓存）
        return
    try:
        embedding = await _embed(query)
        file_name, source_text = _first_source(source_nodes[0]) if source_nodes else ("", "")
        collection = _get_collection()
        collection.upsert(
            ids=[_entry_id(kind, query)],
            documents=[query],
            embeddings=[embedding],
            metadatas=[
                {
                    "kind": kind,
                    "question": query,
                    "answer": _truncate(answer, _ANSWER_MAX_CHARS),
                    "source_file": _truncate(file_name, 200),
                    "source_text": _truncate(source_text, _SOURCE_TEXT_MAX_CHARS),
                    "created_at": time.time(),
                    "hits": 0,
                }
            ],
        )
    except Exception:
        logger.warning("语义缓存写入失败（best-effort，不影响主流程）。", exc_info=True)
        return

    if kind == KIND_AUTO:
        _evict_auto_if_needed(collection)


def _evict_auto_if_needed(collection) -> None:
    """auto 条目超上限时，按命中次数升序驱逐最不常用的。curated 不驱逐。"""
    max_auto = load_env.QA_CACHE_MAX_AUTO_ENTRIES
    try:
        res = collection.get(where={"kind": KIND_AUTO}, include=["metadatas"])
        ids, metas = res.get("ids", []), res.get("metadatas", [])
        if len(ids) <= max_auto:
            return
        ordered = sorted(
            zip(ids, metas), key=lambda pair: int((pair[1] or {}).get("hits", 0))
        )
        victims = [pair[0] for pair in ordered[: len(ids) - max_auto]]
        collection.delete(ids=victims)
        logger.info("语义缓存驱逐 %d 条低命中 auto 条目。", len(victims))
    except Exception:
        logger.warning("语义缓存驱逐失败（best-effort）。", exc_info=True)


async def store_auto(
    query: str, answer: str, source_nodes: list[NodeWithScore]
) -> None:
    """写入自动缓存条目（每次成功问答后调用，未经人工校验）。"""
    await _store(query, answer, source_nodes, KIND_AUTO)


async def store_curated(
    query: str, answer: str, source_nodes: list[NodeWithScore]
) -> None:
    """写入人工沉淀条目（👍 反馈时调用，答案经过用户背书）。"""
    await _store(query, answer, source_nodes, KIND_CURATED)


async def delete_by_question(query: str) -> None:
    """删除同一问题的缓存条目（👎 反馈时调用，不让坏答案继续被命中）。"""
    if not load_env.QA_CACHE_ENABLED:
        return
    query = query.strip()
    if not query:
        return
    try:
        collection = _get_collection()
        res = collection.get(where={"question": query}, include=["metadatas"])
        ids = res.get("ids", [])
        if ids:
            collection.delete(ids=ids)
    except Exception:
        logger.warning("语义缓存按问题删除失败（best-effort）。", exc_info=True)


async def stats() -> dict:
    """缓存统计（``/graph/cache_stats`` 用，也方便演示时一眼看到沉淀规模）。"""
    result = {
        "enabled": load_env.QA_CACHE_ENABLED,
        "collection": load_env.QA_CACHE_COLLECTION,
        "total": 0,
        "auto": 0,
        "curated": 0,
    }
    if not load_env.QA_CACHE_ENABLED:
        return result
    try:
        collection = _get_collection()
        result["total"] = collection.count()
        result["auto"] = len(collection.get(where={"kind": KIND_AUTO}, include=["metadatas"])["ids"])
        result["curated"] = len(
            collection.get(where={"kind": KIND_CURATED}, include=["metadatas"])["ids"]
        )
    except Exception:
        logger.warning("语义缓存统计失败（best-effort）。", exc_info=True)
    return result
