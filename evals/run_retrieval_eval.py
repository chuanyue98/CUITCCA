#!/usr/bin/env python
"""检索质量基线评测：hit-rate / MRR。

加载现有 Chroma 索引（和线上问答同一套 embedding 配置），对
evals/golden.seed.jsonl 里的每个问题做 top-k 检索，判断检索结果里是否命中
golden 条目标注的 expected_sources（按文件名匹配 node 的 metadata），
统计 hit-rate 和 MRR，写一份 JSON 报告到 evals/results/。

只用到 embed_model（本地 HuggingFace 模型），不需要 LLM，所以不需要配置
OPENAI_API_KEY 也能跑（前提是本地已经有 data/chroma_db 索引数据）。

用法:
    uv run python evals/run_retrieval_eval.py
    uv run python evals/run_retrieval_eval.py --top-k 3 --collection test-index

如果本地没有 Chroma 索引数据（比如 CI 环境、全新 checkout），会打印提示并
以 exit code 0 优雅退出——这是给 .github/workflows/evals.yml 用的，见
evals/README.md 的 CI 说明。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
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
# 与线上主查询路径一致：backend/app/handlers/graph_builder.py 里
# _build_query_engine 无论走单索引还是 RouterQueryEngine 路径，
# similarity_top_k 都是 5。
DEFAULT_TOP_K = 5


def _index_data_available() -> bool:
    """粗略判断本地是否有可用的 Chroma 索引数据，不需要就直接退出，避免在
    CI/全新 checkout 里尝试加载 embedding 模型、连网下载等重操作。"""
    from configs.load_env import chroma_db_path

    if not os.path.isdir(chroma_db_path):
        return False
    # PersistentClient 的数据目录里应该有 sqlite 文件；空目录当没有数据处理。
    return any(os.scandir(chroma_db_path))


def _detect_collection(explicit: str | None) -> str | None:
    from handlers.vector_store import list_index_names

    names = list_index_names()
    if explicit:
        if explicit not in names:
            print(f"[run_retrieval_eval] 指定的 collection {explicit!r} 不存在。当前可用: {names}")
            return None
        return explicit
    if len(names) == 1:
        return names[0]
    if not names:
        return None
    print(f"[run_retrieval_eval] data/chroma_db 下有多个 collection {names}，请用 --collection 指定一个。")
    return None


def _evaluate_one(item: dict, nodes_with_scores) -> dict:
    expected_sources = item.get("expected_sources") or []
    rank, matched_source = first_hit_rank(expected_sources, nodes_with_scores)
    retrieved = format_retrieved(nodes_with_scores)

    hit = rank is not None
    reciprocal_rank = 1.0 / rank if rank is not None else 0.0
    return {
        "id": item["id"],
        "question": item["question"],
        "category": item.get("category", "uncategorized"),
        "expected_sources": expected_sources,
        "hit": hit,
        "rank": rank,
        "reciprocal_rank": reciprocal_rank,
        "matched_source": matched_source,
        "retrieved": retrieved,
    }


def run_eval(golden_path: Path, collection_name: str | None, top_k: int) -> dict | None:
    """跑一次完整的检索评测，返回结果 dict；如果索引/数据不可用返回 None。"""
    from configs.llm_predictor import init_settings
    from handlers.vector_store import build_index_from_collection, get_or_create_collection

    resolved_name = _detect_collection(collection_name)
    if resolved_name is None:
        return None

    collection = get_or_create_collection(resolved_name)
    try:
        has_data = collection.count() > 0
    except Exception:
        has_data = False
    if not has_data:
        print(f"[run_retrieval_eval] collection {resolved_name!r} 是空的，没有可评测的数据。")
        return None

    # 只需要 embed_model 就能构建 retriever。init_settings() 同时会配置
    # Settings.llm，但检索阶段用不到 LLM，即使 OPENAI_API_KEY 没配置也不影响
    # 这里的评测结果（只会在真正调用 LLM 生成回答时才报错）。
    init_settings()

    index = build_index_from_collection(collection)
    retriever = index.as_retriever(similarity_top_k=top_k)

    golden = load_jsonl(golden_path)
    details = [_evaluate_one(item, retriever.retrieve(item["question"])) for item in golden]

    ranks = [d["rank"] for d in details]
    overall_hit_rate = hit_rate_at(ranks, top_k)
    overall_mrr = mrr_at(ranks, top_k)

    by_category: dict[str, dict] = {}
    for d in details:
        cat = d["category"]
        bucket = by_category.setdefault(cat, {"count": 0, "hits": 0, "reciprocal_rank_sum": 0.0})
        bucket["count"] += 1
        bucket["hits"] += int(d["hit"])
        bucket["reciprocal_rank_sum"] += d["reciprocal_rank"]

    category_scores = {
        cat: {
            "count": b["count"],
            "hit_rate": b["hits"] / b["count"] if b["count"] else 0.0,
            "mrr": b["reciprocal_rank_sum"] / b["count"] if b["count"] else 0.0,
        }
        for cat, b in sorted(by_category.items())
    }

    return {
        "collection": resolved_name,
        "top_k": top_k,
        "golden_path": str(golden_path),
        "num_questions": len(details),
        "overall": {"hit_rate": overall_hit_rate, "mrr": overall_mrr},
        "by_category": category_scores,
        "details": details,
    }


def _print_summary(result: dict) -> None:
    print()
    print(
        f"Retrieval eval — collection={result['collection']!r} top_k={result['top_k']} "
        f"questions={result['num_questions']}"
    )
    print("-" * 68)
    print(f"{'overall':<24} hit_rate={result['overall']['hit_rate']:>7.2%}  mrr={result['overall']['mrr']:.3f}")
    print("-" * 68)
    for cat, scores in result["by_category"].items():
        print(f"{cat:<24} hit_rate={scores['hit_rate']:>7.2%}  mrr={scores['mrr']:.3f}  (n={scores['count']})")
    print("-" * 68)
    misses = [d for d in result["details"] if not d["hit"]]
    if misses:
        print(f"{len(misses)} 条未命中:")
        for d in misses:
            print(f"  [{d['id']}] {d['question']}  (期望来源: {d['expected_sources']})")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN, help="golden 数据集路径")
    parser.add_argument("--collection", default=None, help="Chroma collection 名，默认自动探测（只有一个时）")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help=f"检索 top-k，默认 {DEFAULT_TOP_K}")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="结果输出目录")
    args = parser.parse_args()

    if not args.golden.exists():
        print(f"[run_retrieval_eval] golden 数据集不存在: {args.golden}")
        return 1

    bootstrap_backend_path()

    if not _index_data_available():
        print(
            "[run_retrieval_eval] 没有检测到本地 Chroma 索引数据（data/chroma_db 不存在或为空）。"
            "这在 CI / 全新 checkout 里是预期情况——真实的检索评测需要先在本地构建好索引再跑，"
            "详见 evals/README.md。跳过评测。"
        )
        return 0

    try:
        result = run_eval(args.golden, args.collection, args.top_k)
    except Exception as e:
        print(f"[run_retrieval_eval] 评测过程中出错: {e!r}")
        return 1

    if result is None:
        # run_eval 内部已经打印了具体原因（collection 不存在 / 为空 / 有多个需要指定）。
        return 0

    _print_summary(result)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"retrieval_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"结果已写入 {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
