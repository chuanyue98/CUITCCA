#!/usr/bin/env python
"""验证 Phase 3 的 QAWorkflow 检索路径在 campus-corpus 上的检索质量。

``handlers/qa_workflow.py`` 的 ``_build_retriever()`` 在只有一个 collection
时走的是"单索引"分支：``index.as_retriever(similarity_top_k=DEFAULT_SIMILARITY_TOP_K)``
——这和 ``evals/run_retrieval_eval.py`` 内部做的事情是同一行代码，理论上数字
应该完全一致或极接近。这个脚本不是"再发明一遍评测逻辑"，而是拿真实索引数据
把这个"应该一致"的预期实测验证一遍，复用 ``evals/_common.py`` 里 Phase 0/2
就有的 hit-rate/MRR 计算和 ``evals/run_retrieval_eval.py`` 的 collection 探测
逻辑，不重复实现。

用法:
    uv run python evals/run_workflow_retrieval_eval.py --collection campus-corpus

和 run_retrieval_eval.py 一样：只用 embed_model，不需要 LLM/API key；本地没有
索引数据时打印提示并 exit 0。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

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
DEFAULT_TOP_K = 5
HIT_KS = (1, 2, 5)


async def _run(golden_path: Path, collection_name: str | None, top_k: int) -> dict | None:
    import handlers.qa_workflow as qa_workflow
    from configs.llm_predictor import init_settings
    from handlers.vector_store import build_index_from_collection, get_or_create_collection
    from llama_index.core.schema import QueryBundle

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
        print(f"[run_workflow_retrieval_eval] collection {resolved_name!r} 是空的，没有可评测的数据。")
        return None

    init_settings()
    index = build_index_from_collection(collection)
    index.set_index_id(resolved_name)

    # 只塞这一个 index，_build_retriever() 会走单索引分支（不需要 LLM
    # selector），和 run_retrieval_eval.py 用的 index.as_retriever(...) 是
    # 完全一样的调用。
    with patch.object(qa_workflow, "indexes", [index]):
        retriever = qa_workflow._build_retriever(top_k=top_k)
        golden = load_jsonl(golden_path)
        details = []
        for item in golden:
            nodes = await retriever.aretrieve(QueryBundle(query_str=item["question"]))
            expected_sources = item.get("expected_sources") or []
            rank, matched_source = first_hit_rank(expected_sources, nodes)
            details.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "category": item.get("category", "uncategorized"),
                    "expected_sources": expected_sources,
                    "rank": rank,
                    "matched_source": matched_source,
                    "retrieved": format_retrieved(nodes)[:top_k],
                }
            )

    ranks = [d["rank"] for d in details]
    overall = {f"hit_rate@{k}": hit_rate_at(ranks, k) for k in HIT_KS}
    overall[f"mrr@{top_k}"] = mrr_at(ranks, top_k)

    return {
        "collection": resolved_name,
        "top_k": top_k,
        "golden_path": str(golden_path),
        "num_questions": len(details),
        "retriever_path": "handlers.qa_workflow._build_retriever (single-index branch)",
        "overall": overall,
        "details": details,
    }


def _print_summary(result: dict) -> None:
    print()
    print(
        f"Workflow retrieval eval — collection={result['collection']!r} top_k={result['top_k']} "
        f"questions={result['num_questions']}"
    )
    print(f"retriever path: {result['retriever_path']}")
    print("-" * 68)
    for key, value in result["overall"].items():
        print(f"{key:<12} {value:.3f}" if "mrr" in key else f"{key:<12} {value:.2%}")
    print("-" * 68)
    misses = [d for d in result["details"] if d["rank"] is None]
    if misses:
        print(f"{len(misses)} 条未命中:")
        for d in misses:
            print(f"  [{d['id']}] {d['question']}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN, help="golden 数据集路径")
    parser.add_argument("--collection", default="campus-corpus", help="Chroma collection 名（默认 campus-corpus）")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help=f"检索 top-k，默认 {DEFAULT_TOP_K}")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="结果输出目录")
    args = parser.parse_args()

    if not args.golden.exists():
        print(f"[run_workflow_retrieval_eval] golden 数据集不存在: {args.golden}")
        return 1

    bootstrap_backend_path()

    from evals.run_retrieval_eval import _index_data_available

    if not _index_data_available():
        print(
            "[run_workflow_retrieval_eval] 没有检测到本地 Chroma 索引数据，跳过评测"
            "（CI/全新 checkout 里是预期情况，见 evals/README.md）。"
        )
        return 0

    try:
        result = asyncio.run(_run(args.golden, args.collection, args.top_k))
    except Exception as e:
        print(f"[run_workflow_retrieval_eval] 评测过程中出错: {e!r}")
        return 1

    if result is None:
        return 0

    _print_summary(result)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output_dir / f"workflow_retrieval_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"结果已写入 {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
