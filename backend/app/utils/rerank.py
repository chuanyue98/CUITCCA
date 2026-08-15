"""条件触发式 Rerank 后处理器：仅在向量检索置信度不足时才触发 cross-encoder 重排。

设计目标：
- 默认关闭，不改变现有线上行为。
- 打开后，向量召回候选数由 RERANK_RECALL_K 控制；
  若 top1 分数 >= RERANK_SCORE_THRESHOLD，直接截断到 RERANK_TOP_N 返回；
  否则对全部候选做 rerank，取 RERANK_TOP_N。
- Reranker 延迟加载，首次触发时才 import sentence-transformers。

用法:
    from utils.rerank import ConditionalRerankPostprocessor
    qe = index.as_query_engine(
        similarity_top_k=...,
        node_postprocessors=[ConditionalRerankPostprocessor()],
    )
"""
from __future__ import annotations

import logging
import time

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle

logger = logging.getLogger(__name__)

_reranker_instance = None


def _get_reranker():
    global _reranker_instance
    if _reranker_instance is None:
        import configs.load_env as load_env
        from llama_index.core.postprocessor import SentenceTransformerRerank
        _reranker_instance = SentenceTransformerRerank(
            model=load_env.RERANKER_MODEL,
            top_n=load_env.RERANK_TOP_N,
        )
    return _reranker_instance


class ConditionalRerankPostprocessor(BaseNodePostprocessor):
    def __init__(self) -> None:
        super().__init__()
        self._reranker = None

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: QueryBundle | None = None,
    ) -> list[NodeWithScore]:
        import configs.load_env as load_env

        if not load_env.RERANK_ENABLED:
            return nodes[: load_env.RERANK_TOP_N]

        if not nodes:
            return nodes

        # 已知问题（2026-08，实现 handlers/auto_router.py 自动路由时在真实语料
        # 上测出来的，如实记录、这次不改）：这里的 top1_score 是**融合后**的
        # RRF 分数（混合检索 BM25+dense 的 RRF 融合结果），不是 cross-encoder
        # 重排分数。campus-corpus 实测下来，RRF top1 无论问题是否被语料覆盖都
        # 落在 0.026~0.033 这个极窄区间——完全没有区分度，恒小于
        # RERANK_SCORE_THRESHOLD=0.75，也就是"top1 >= 阈值时跳过 rerank"这个
        # 条件分支在生产环境里事实上从未被触发过，rerank 其实一直在无条件
        # 触发（等价于 RERANK_ENABLED 打开后 always-on，只是顶着"条件触发"的
        # 名字）。这不是这次改动引入的新问题，是在验证自动路由分数区分度时
        # 顺带发现的既有行为；不在这次改动里修（改这个阈值/触发逻辑会直接
        # 影响线上检索质量基线和已归档的评测数据，需要单独一轮评测验证，
        # 不应该夹在"去掉模式切换器"这个不相关的改动里悄悄改掉）。真正有
        # 区分度的是重排*之后*的 cross-encoder 分数，用于路由判断见
        # handlers/auto_router.py 和 configs/load_env.py 的 AUTO_ROUTE_
        # SCORE_THRESHOLD 注释。
        top1_score = nodes[0].score or 0.0
        if top1_score >= load_env.RERANK_SCORE_THRESHOLD:
            logger.debug(
                "rerank skipped: top1=%.3f >= threshold=%.2f",
                top1_score,
                load_env.RERANK_SCORE_THRESHOLD,
            )
            return nodes[: load_env.RERANK_TOP_N]

        if len(nodes) <= load_env.RERANK_TOP_N:
            logger.debug(
                "rerank skipped: recall=%d <= top_n=%d",
                len(nodes),
                load_env.RERANK_TOP_N,
            )
            return nodes

        reranker = _get_reranker()
        q = query_bundle.query_str if query_bundle else ""
        t0 = time.perf_counter()
        reranked = reranker.postprocess_nodes(nodes, query_bundle=query_bundle or QueryBundle(q))
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "rerank triggered: top1=%.3f < %.2f, recall=%d -> top_n=%d, latency=%.0fms",
            top1_score,
            load_env.RERANK_SCORE_THRESHOLD,
            len(nodes),
            load_env.RERANK_TOP_N,
            ms,
        )
        return reranked
