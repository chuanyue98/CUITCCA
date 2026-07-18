#!/usr/bin/env python
"""混合检索 A/B/C 评测：量化"加 BM25+dense RRF 融合值不值得"。

对 golden 数据集的每个问题，在同一个 Chroma collection 上跑三组：

- A 基线：纯向量检索 top_k=5（与线上主查询路径一致，即 run_retrieval_eval 的配置）
- B 混合检索：BM25（jieba 分词）+ dense，RRF 融合，最终 top_k=5
  （见 handlers/hybrid_retriever.py，两路各自先宽召回再融合截断）
- C 混合检索 + rerank：混合检索先融合出 recall_k=20 条，再用本地
  cross-encoder（默认 BAAI/bge-reranker-v2-m3）重排取 top 5——这是 Phase C
  打算默认上线的目标配置，在这里先验证组合效果，即使 Phase C 还没正式落地。

三组都算 hit_rate@1/@2/@5 和 MRR@5（文件级命中，逻辑与 run_retrieval_eval/
run_rerank_eval 一致，共用 evals/_common.py），并分别记录每题检索耗时。

C 组依赖 sentence-transformers（主依赖，`uv sync` 就会装）。
reranker 模型约 2.2GB，首次运行会从 HuggingFace 下载。

用法:
    uv run python evals/run_hybrid_eval.py --collection campus-corpus
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
    hit_rate_at,
    load_jsonl,
    mrr_at,
)

DEFAULT_GOLDEN = EVALS_DIR / "golden.seed.jsonl"
DEFAULT_RESULTS_DIR = EVALS_DIR / "results"
DEFAULT_TOP_K = 5  # 与线上主查询路径一致
DEFAULT_RECALL_K = 20  # rerank 前的融合召回数，和 run_rerank_eval 保持一致口径
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


def run_abc_eval(
    golden_path: Path,
    collection_name: str | None,
    top_k: int,
    recall_k: int,
    reranker_model: str,
    skip_rerank: bool,
) -> dict | None:
    """跑一次 A/B/C 评测，返回结果 dict；索引/数据不可用时返回 None。"""
    from configs.llm_predictor import init_settings
    from handlers.hybrid_retriever import _build_hybrid_retriever
    from handlers.vector_store import build_index_from_collection, get_or_create_collection

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
        print(f"[run_hybrid_eval] collection {resolved_name!r} 是空的，没有可评测的数据。")
        return None

    init_settings()
    index = build_index_from_collection(collection)

    retriever_a = index.as_retriever(similarity_top_k=top_k)
    # _build_hybrid_retriever 是内部函数，不经过 HYBRID_RETRIEVAL_ENABLED 开关
    # ——评测脚本要的是"这套机制本身好不好"，不受生产开关状态影响。
    retriever_b = _build_hybrid_retriever(index, top_k)

    reranker = None
    retriever_c_recall = None
    if not skip_rerank:
        from llama_index.core.postprocessor import SentenceTransformerRerank

        print(f"[run_hybrid_eval] 加载 reranker {reranker_model}（首次运行需下载约 2.2GB）...")
        reranker = SentenceTransformerRerank(model=reranker_model, top_n=top_k)
        retriever_c_recall = _build_hybrid_retriever(index, recall_k)

    golden = load_jsonl(golden_path)

    # 预热：首次调用包含模型加载/编译开销（embedding、jieba 词典、reranker
    # 模型），不应计入单题延迟。
    warmup_q = golden[0]["question"]
    retriever_a.retrieve(warmup_q)
    retriever_b.retrieve(warmup_q)
    if reranker is not None:
        from llama_index.core.schema import QueryBundle

        warmup_recalled = retriever_c_recall.retrieve(warmup_q)
        reranker.postprocess_nodes(warmup_recalled, query_bundle=QueryBundle(warmup_q))

    details = []
    ranks_a: list[int | None] = []
    ranks_b: list[int | None] = []
    ranks_c: list[int | None] = []
    lat_a: list[float] = []
    lat_b: list[float] = []
    lat_c: list[float] = []

    for item in golden:
        question = item["question"]
        expected = item.get("expected_sources") or []

        t0 = time.perf_counter()
        nodes_a = retriever_a.retrieve(question)
        ms_a = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        nodes_b = retriever_b.retrieve(question)
        ms_b = (time.perf_counter() - t0) * 1000

        rank_a, _ = first_hit_rank(expected, nodes_a)
        rank_b, _ = first_hit_rank(expected, nodes_b)
        ranks_a.append(rank_a)
        ranks_b.append(rank_b)
        lat_a.append(ms_a)
        lat_b.append(ms_b)

        entry = {
            "id": item["id"],
            "question": question,
            "category": item.get("category", "uncategorized"),
            "expected_sources": expected,
            "rank_baseline": rank_a,
            "rank_hybrid": rank_b,
            "latency_ms_baseline": round(ms_a, 1),
            "latency_ms_hybrid": round(ms_b, 1),
        }

        if reranker is not None:
            from llama_index.core.schema import QueryBundle

            t0 = time.perf_counter()
            recalled_c = retriever_c_recall.retrieve(question)
            nodes_c = reranker.postprocess_nodes(recalled_c, query_bundle=QueryBundle(question))
            ms_c = (time.perf_counter() - t0) * 1000

            rank_c, _ = first_hit_rank(expected, nodes_c)
            ranks_c.append(rank_c)
            lat_c.append(ms_c)
            entry["rank_hybrid_rerank"] = rank_c
            entry["latency_ms_hybrid_rerank"] = round(ms_c, 1)

        details.append(entry)

    result = {
        "collection": resolved_name,
        "golden_path": str(golden_path),
        "num_questions": len(details),
        "config": {
            "baseline": {"similarity_top_k": top_k},
            "hybrid": {"similarity_top_k": top_k},
            "hybrid_rerank": (
                {"recall_k": recall_k, "top_n": top_k, "model": reranker_model} if reranker is not None else None
            ),
        },
        "baseline": _arm_metrics(ranks_a, lat_a, top_k),
        "hybrid": _arm_metrics(ranks_b, lat_b, top_k),
        "details": details,
    }
    if reranker is not None:
        result["hybrid_rerank"] = _arm_metrics(ranks_c, lat_c, top_k)
    return result


def _print_summary(result: dict) -> None:
    top_k = result["config"]["baseline"]["similarity_top_k"]
    arms = [("A 基线", "baseline"), ("B 混合检索", "hybrid")]
    if "hybrid_rerank" in result:
        arms.append(("C 混合+rerank", "hybrid_rerank"))

    print()
    print(f"Hybrid A/B/C — collection={result['collection']!r} questions={result['num_questions']}")
    print("-" * 88)
    header = f"{'指标':<16}" + "".join(f"{label:>16}" for label, _ in arms)
    print(header)
    print("-" * 88)
    for k in HIT_KS:
        row = f"{'hit_rate@' + str(k):<16}"
        for _, key in arms:
            row += f"{result[key]['hit_rate'][f'@{k}']:>15.2%} "
        print(row)
    mrr_key = f"mrr@{top_k}"
    row = f"{mrr_key:<16}"
    for _, key in arms:
        row += f"{result[key][mrr_key]:>15.3f} "
    print(row)
    for stat in ("avg", "p50", "max"):
        row = f"{'latency_' + stat + '(ms)':<16}"
        for _, key in arms:
            row += f"{result[key]['latency_ms'][stat]:>15.1f} "
        print(row)
    print("-" * 88)

    misses_b = [d for d in result["details"] if d["rank_hybrid"] is None]
    if misses_b:
        print(f"混合检索仍未命中的题目 ({len(misses_b)} 条):")
        for d in misses_b:
            print(f"  [{d['id']}] {d['question']} (基线排名: {d['rank_baseline']})")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN, help="golden 数据集路径")
    parser.add_argument("--collection", default=None, help="Chroma collection 名（评测语料建议 campus-corpus）")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help=f"三组最终取的结果数，默认 {DEFAULT_TOP_K}")
    parser.add_argument(
        "--recall-k", type=int, default=DEFAULT_RECALL_K, help=f"C 组 rerank 前的融合召回数，默认 {DEFAULT_RECALL_K}"
    )
    parser.add_argument(
        "--reranker-model", default=DEFAULT_RERANKER, help=f"C 组 cross-encoder 模型，默认 {DEFAULT_RERANKER}"
    )
    parser.add_argument("--skip-rerank", action="store_true", help="只跑 A/B 两组，不跑 C（不需要 rerank 依赖）")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="结果输出目录")
    args = parser.parse_args()

    if not args.golden.exists():
        print(f"[run_hybrid_eval] golden 数据集不存在: {args.golden}")
        return 1

    bootstrap_backend_path()

    from evals.run_retrieval_eval import _index_data_available

    if not _index_data_available():
        print(
            "[run_hybrid_eval] 没有检测到本地 Chroma 索引数据（data/chroma_db 不存在或为空），跳过评测。"
            "真实评测需在有索引数据的机器上跑，见 evals/README.md。"
        )
        return 0

    skip_rerank = args.skip_rerank
    if not skip_rerank:
        try:
            from llama_index.core.postprocessor import SentenceTransformerRerank  # noqa: F401
        except ImportError:
            print("[run_hybrid_eval] 缺少 rerank 依赖，C 组将跳过（只跑 A/B）。如需 C 组: uv sync")
            skip_rerank = True

    try:
        result = run_abc_eval(args.golden, args.collection, args.top_k, args.recall_k, args.reranker_model, skip_rerank)
    except Exception as e:
        print(f"[run_hybrid_eval] 评测过程中出错: {e!r}")
        return 1

    if result is None:
        return 0

    _print_summary(result)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"hybrid_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"结果已写入 {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
