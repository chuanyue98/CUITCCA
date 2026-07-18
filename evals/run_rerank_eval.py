#!/usr/bin/env python
"""Rerank A/B 评测：量化"加 cross-encoder reranker 值不值得"。

对 golden 数据集的每个问题，在同一个 Chroma collection 上跑两组：

- A 基线：向量检索 top_k=5（与线上主查询路径一致，即 run_retrieval_eval 的配置）
- B rerank：向量检索先召回 recall_k=20，再用本地 cross-encoder
  （默认 BAAI/bge-reranker-v2-m3，与线上 bge-m3 embedding 同家族）重排取 top 5

两组都算 hit_rate@1/@2/@5 和 MRR@5（文件级命中，逻辑与 run_retrieval_eval 一致，
共用 evals/_common.py 里的 first_hit_rank / hit_rate_at / mrr_at），并分别记录
每题检索耗时，量化 rerank 的延迟代价。

依赖 sentence-transformers（主依赖，`uv sync` 就会装）。
reranker 模型约 2.2GB，首次运行会从 HuggingFace 下载。

用法:
    uv run python evals/run_rerank_eval.py --collection campus-corpus
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals._common import (  # noqa: E402
    EVALS_DIR,
    bootstrap_backend_path,
    first_hit_rank,
    format_retrieved,
    hit_rate_at,
    load_jsonl,
    mrr_at,
)

DEFAULT_GOLDEN = EVALS_DIR / "golden.seed.jsonl"
DEFAULT_RESULTS_DIR = EVALS_DIR / "results"
DEFAULT_TOP_K = 5  # 与线上主查询路径一致
DEFAULT_RECALL_K = 20  # rerank 前的向量召回数
DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"
HIT_KS = (1, 2, 5)


def _arm_metrics(ranks: list[int | None], latencies_ms: list[float], top_k: int) -> dict:
    return {
        "hit_rate": {f"@{k}": hit_rate_at(ranks, k) for k in HIT_KS},
        f"mrr@{top_k}": mrr_at(ranks, top_k),
        "latency_ms": {
            "avg": statistics.mean(latencies_ms) if latencies_ms else 0.0,
            "max": max(latencies_ms) if latencies_ms else 0.0,
            "p50": statistics.median(latencies_ms) if latencies_ms else 0.0,
        },
    }


def run_ab_eval(
    golden_path: Path,
    collection_name: str | None,
    top_k: int,
    recall_k: int,
    reranker_model: str,
) -> dict | None:
    """跑一次 A/B 评测，返回结果 dict；索引/数据不可用时返回 None。"""
    from configs.llm_predictor import init_settings
    from handlers.vector_store import build_index_from_collection, get_or_create_collection
    from llama_index.core.postprocessor import SentenceTransformerRerank
    from llama_index.core.schema import QueryBundle

    # 复用 run_retrieval_eval 的 collection 探测逻辑
    from evals.run_retrieval_eval import _detect_collection

    resolved_name = _detect_collection(collection_name)
    if resolved_name is None:
        return None

    collection = get_or_create_collection(resolved_name)
    try:
        has_data = collection.count() > 0
    except Exception:
        has_data = False
    if not has_data:
        print(f"[run_rerank_eval] collection {resolved_name!r} 是空的，没有可评测的数据。")
        return None

    init_settings()
    index = build_index_from_collection(collection)
    retriever_a = index.as_retriever(similarity_top_k=top_k)
    retriever_b = index.as_retriever(similarity_top_k=recall_k)

    print(f"[run_rerank_eval] 加载 reranker {reranker_model}（首次运行需下载约 2.2GB）...")
    reranker = SentenceTransformerRerank(model=reranker_model, top_n=top_k)

    golden = load_jsonl(golden_path)

    # 预热：首次调用包含模型加载/编译开销，不应计入单题延迟
    warmup_q = golden[0]["question"]
    warmup_nodes = retriever_b.retrieve(warmup_q)
    reranker.postprocess_nodes(warmup_nodes, query_bundle=QueryBundle(warmup_q))
    retriever_a.retrieve(warmup_q)

    details = []
    ranks_a: list[int | None] = []
    ranks_b: list[int | None] = []
    lat_a: list[float] = []
    lat_b: list[float] = []

    for item in golden:
        question = item["question"]
        expected = item.get("expected_sources") or []

        t0 = time.perf_counter()
        nodes_a = retriever_a.retrieve(question)
        ms_a = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        recalled = retriever_b.retrieve(question)
        nodes_b = reranker.postprocess_nodes(recalled, query_bundle=QueryBundle(question))
        ms_b = (time.perf_counter() - t0) * 1000

        rank_a, _ = first_hit_rank(expected, nodes_a)
        rank_b, _ = first_hit_rank(expected, nodes_b)
        # 记录正确来源在纯向量召回 20 条里的原始排名，便于分析 rerank 提升幅度
        rank_recall, _ = first_hit_rank(expected, recalled)

        ranks_a.append(rank_a)
        ranks_b.append(rank_b)
        lat_a.append(ms_a)
        lat_b.append(ms_b)

        details.append(
            {
                "id": item["id"],
                "question": question,
                "category": item.get("category", "uncategorized"),
                "expected_sources": expected,
                "rank_baseline": rank_a,
                "rank_recall20": rank_recall,
                "rank_reranked": rank_b,
                "latency_ms_baseline": round(ms_a, 1),
                "latency_ms_rerank": round(ms_b, 1),
                "top_reranked": format_retrieved(nodes_b),
            }
        )

    return {
        "collection": resolved_name,
        "golden_path": str(golden_path),
        "num_questions": len(details),
        "config": {
            "baseline": {"similarity_top_k": top_k},
            "rerank": {"recall_k": recall_k, "top_n": top_k, "model": reranker_model},
        },
        "baseline": _arm_metrics(ranks_a, lat_a, top_k),
        "rerank": _arm_metrics(ranks_b, lat_b, top_k),
        "details": details,
    }


def _print_summary(result: dict) -> None:
    top_k = result["config"]["baseline"]["similarity_top_k"]
    recall_k = result["config"]["rerank"]["recall_k"]
    a = result["baseline"]
    b = result["rerank"]

    print()
    print(
        f"Rerank A/B — collection={result['collection']!r} questions={result['num_questions']} "
        f"(A: top_k={top_k} | B: recall {recall_k} -> rerank top {top_k})"
    )
    print("-" * 76)
    header = f"{'指标':<16} {'A 基线':>12} {'B rerank':>12} {'差值':>10}"
    print(header)
    print("-" * 76)
    for k in HIT_KS:
        va, vb = a["hit_rate"][f"@{k}"], b["hit_rate"][f"@{k}"]
        print(f"{'hit_rate@' + str(k):<16} {va:>11.2%} {vb:>11.2%} {vb - va:>+9.2%}")
    mrr_key = f"mrr@{top_k}"
    print(f"{mrr_key:<16} {a[mrr_key]:>12.3f} {b[mrr_key]:>12.3f} {b[mrr_key] - a[mrr_key]:>+10.3f}")
    for stat in ("avg", "p50", "max"):
        va, vb = a["latency_ms"][stat], b["latency_ms"][stat]
        print(f"{'latency_' + stat + '(ms)':<16} {va:>12.1f} {vb:>12.1f} {vb - va:>+10.1f}")
    print("-" * 76)

    moved = [d for d in result["details"] if d["rank_baseline"] != d["rank_reranked"]]
    if moved:
        print("排名变化的题目 (基线 -> rerank，括号内是召回20条里的原始排名):")
        for d in moved:
            print(
                f"  [{d['id']}] {d['rank_baseline']} -> {d['rank_reranked']} "
                f"(recall20: {d['rank_recall20']})  {d['question']}"
            )
    misses = [d for d in result["details"] if d["rank_reranked"] is None]
    if misses:
        print("rerank 后仍未进 top 5 的题目:")
        for d in misses:
            print(f"  [{d['id']}] {d['question']} (recall20 排名: {d['rank_recall20']})")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN, help="golden 数据集路径")
    parser.add_argument("--collection", default=None, help="Chroma collection 名（评测语料建议 campus-corpus）")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help=f"两组最终取的结果数，默认 {DEFAULT_TOP_K}")
    parser.add_argument(
        "--recall-k", type=int, default=DEFAULT_RECALL_K, help=f"rerank 前召回数，默认 {DEFAULT_RECALL_K}"
    )
    parser.add_argument(
        "--reranker-model", default=DEFAULT_RERANKER, help=f"cross-encoder 模型，默认 {DEFAULT_RERANKER}"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="结果输出目录")
    args = parser.parse_args()

    if not args.golden.exists():
        print(f"[run_rerank_eval] golden 数据集不存在: {args.golden}")
        return 1

    bootstrap_backend_path()

    from evals.run_retrieval_eval import _index_data_available

    if not _index_data_available():
        print(
            "[run_rerank_eval] 没有检测到本地 Chroma 索引数据（data/chroma_db 不存在或为空），跳过评测。"
            "真实评测需在有索引数据的机器上跑，见 evals/README.md。"
        )
        return 0

    try:
        from llama_index.core.postprocessor import SentenceTransformerRerank  # noqa: F401
    except ImportError:
        print("[run_rerank_eval] 缺少 rerank 依赖，请先执行: uv sync")
        return 1

    try:
        result = run_ab_eval(args.golden, args.collection, args.top_k, args.recall_k, args.reranker_model)
    except Exception as e:
        print(f"[run_rerank_eval] 评测过程中出错: {e!r}")
        return 1

    if result is None:
        return 0

    _print_summary(result)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"rerank_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"结果已写入 {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
