#!/usr/bin/env python
"""从现有 Chroma 索引里的文档批量生成 QA 候选，写到 evals/golden.candidates.jsonl。

复用项目已有的 QA 生成逻辑（backend/app/utils/llama.py 里的
generate_qa_batched / formatted_pairs），不重新造轮子。

产出的候选题 **不能直接当 golden 用**——必须人工逐条审核（问题是否清楚、
答案是否完整准确、expected_sources 是否标对），确认无误后手动搬进
evals/golden.seed.jsonl。详见 evals/README.md 的"golden 数据集维护规则"。

需要一个可用的 LLM（走项目现有的 configs.load_env / configs.llm_predictor
配置，即 .env 里的 OPENAI_API_KEY / OPENAI_API_BASE / OPENAI_MODEL）。

用法:
    uv run python evals/generate_golden.py --collection test-index --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals._common import EVALS_DIR, bootstrap_backend_path, strip_uuid_prefix, write_jsonl  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("generate_golden")

DEFAULT_OUTPUT = EVALS_DIR / "golden.candidates.jsonl"


def _group_docs_by_file(collection) -> dict[str, str]:
    """把 collection 里的所有 chunk 按 file_name（去掉 uuid 前缀）分组，
    拼回近似的整篇文档文本，用于喂给 QA 生成。"""
    data = collection.get(include=["metadatas", "documents"])
    ids = data.get("ids") or []
    metadatas = data.get("metadatas") or []
    documents = data.get("documents") or []

    grouped: dict[str, list[str]] = {}
    for i in range(len(ids)):
        meta = metadatas[i] or {}
        text = documents[i] or ""
        if not text.strip():
            continue
        file_name = meta.get("file_name") or meta.get("doc_id") or f"unknown_{ids[i]}"
        clean_name = strip_uuid_prefix(file_name)
        grouped.setdefault(clean_name, []).append(text)

    return {name: "\n".join(chunks) for name, chunks in grouped.items()}


async def _generate_for_file(file_name: str, content: str, prompt: str | None) -> list[dict]:
    from utils.llama import formatted_pairs, generate_qa_batched

    raw_blocks = await generate_qa_batched(content, prompt=prompt)
    qa_pairs = formatted_pairs(raw_blocks)

    candidates = []
    for i in range(0, len(qa_pairs) - 1, 2):
        question = qa_pairs[i]
        answer = qa_pairs[i + 1]
        if not question or not answer:
            continue
        candidates.append(
            {
                "id": f"cand_{uuid.uuid4().hex[:8]}",
                "question": question,
                "expected_answer": answer,
                "expected_sources": [file_name],
                "category": "candidate",
            }
        )
    return candidates


async def _run(collection_name: str, limit: int, prompt: str | None) -> list[dict]:
    from configs.llm_predictor import init_settings
    from handlers.vector_store import get_or_create_collection, list_index_names

    available = list_index_names()
    if collection_name not in available:
        logger.error(
            "collection %r 不存在。当前可用 collection: %s。请用 --collection 指定一个存在的 collection。",
            collection_name,
            available,
        )
        return []

    init_settings()

    collection = get_or_create_collection(collection_name)
    docs_by_file = _group_docs_by_file(collection)
    if not docs_by_file:
        logger.warning("collection %r 里没有任何文档，无法生成候选题。", collection_name)
        return []

    file_names = list(docs_by_file.keys())
    if limit > 0:
        file_names = file_names[:limit]

    logger.info("将对 %d 个文档生成 QA 候选: %s", len(file_names), file_names)

    all_candidates: list[dict] = []
    for file_name in file_names:
        content = docs_by_file[file_name]
        try:
            candidates = await _generate_for_file(file_name, content, prompt)
        except Exception:
            logger.exception("为文档 %r 生成 QA 候选失败，跳过", file_name)
            continue
        logger.info("  %s -> %d 条候选", file_name, len(candidates))
        all_candidates.extend(candidates)

    return all_candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--collection", default="test-index", help="Chroma collection 名（默认 test-index）")
    parser.add_argument("--limit", type=int, default=5, help="最多处理多少个文档，0 表示不限（默认 5）")
    parser.add_argument("--prompt", default=None, help="自定义 QA 生成指令，默认用 generate_qa_batched 的内置指令")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="候选题输出路径")
    args = parser.parse_args()

    bootstrap_backend_path()

    try:
        candidates = asyncio.run(_run(args.collection, args.limit, args.prompt))
    except Exception:
        logger.exception(
            "生成候选题失败，很可能是 LLM 未配置好（检查 .env 里的 OPENAI_API_KEY / "
            "OPENAI_API_BASE / OPENAI_MODEL），或者 data/chroma_db 索引不存在。"
        )
        return 1

    if not candidates:
        logger.warning("没有生成任何候选题，不写文件。")
        return 0

    write_jsonl(args.output, candidates)
    logger.info(
        "已写入 %d 条候选到 %s —— 记得人工审核后再搬进 evals/golden.seed.jsonl，不要直接用于评分。",
        len(candidates),
        args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
