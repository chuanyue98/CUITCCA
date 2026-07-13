#!/usr/bin/env python
"""一次性导入脚本：把仓库里未被索引的真实文档全量导入 Chroma collection `campus-corpus`。

服务于评测基线（Phase 0），不是线上功能。与线上上传路径保持一致的解析/切块行为：
和 handlers/index_crud.py 的 insert_into_index 一样，走 utils/llama.py 的
get_nodes_from_file（SimpleDirectoryReader + SentenceSplitter.from_defaults()），
embedding 用 configs/llm_predictor.py 的 init_settings()（BAAI/bge-m3，本地）。

与线上的两点刻意差异（都是为了评测数据干净）：
- metadata 的 file_name 是原始文件名（直接在原地读取文件，不做 uuid 前缀拷贝）。
- 按文件内容 sha256 去重：两个数据源里有大量互为镜像的重复文件，只导入第一份，
  跳过的重复项在 stdout 报告。

可重复运行：每次先删掉重建 `campus-corpus` collection，不会越跑越重。

用法:
    uv run python evals/ingest_corpus.py
    uv run python evals/ingest_corpus.py --collection campus-corpus
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals._common import REPO_ROOT, bootstrap_backend_path  # noqa: E402

DEFAULT_COLLECTION = "campus-corpus"
SOURCE_DIRS = (
    REPO_ROOT / "信息搜集汇总",
    REPO_ROOT / "data" / "upload_files",
)
# 老索引的 store json（vector_store.json / docstore.json 等）混在语料目录里，
# 按扩展名过滤即可排除（.json 不在 ALLOWED_EXTENSIONS 里）。


def _collect_files(source_dirs: tuple[Path, ...], allowed_extensions: set[str]) -> list[Path]:
    files: list[Path] = []
    for root in source_dirs:
        if not root.is_dir():
            print(f"[ingest] 警告: 数据源目录不存在，跳过: {root}")
            continue
        files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in allowed_extensions)
    # 排序保证可重复运行时"哪份重复文件胜出"是确定的（信息搜集汇总 在前）
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--collection", default=DEFAULT_COLLECTION, help=f"目标 collection 名（默认 {DEFAULT_COLLECTION}）"
    )
    args = parser.parse_args()

    bootstrap_backend_path()

    from configs.llm_predictor import init_settings
    from configs.load_env import ALLOWED_EXTENSIONS
    from handlers.vector_store import (
        build_index_from_collection,
        delete_collection,
        get_or_create_collection,
        list_index_names,
    )
    from utils.llama import get_nodes_from_file

    files = _collect_files(SOURCE_DIRS, {ext.lower() for ext in ALLOWED_EXTENSIONS})
    if not files:
        print("[ingest] 两个数据源目录下没有任何可解析文件，退出。")
        return 1
    print(f"[ingest] 发现 {len(files)} 个候选文件（扩展名过滤: {sorted(ALLOWED_EXTENSIONS)}）")

    # 重建 collection，保证可重复运行
    if args.collection in list_index_names():
        print(f"[ingest] collection {args.collection!r} 已存在，删除重建。")
        delete_collection(args.collection)
    collection = get_or_create_collection(args.collection)

    init_settings()
    index = build_index_from_collection(collection)
    index.set_index_id(args.collection)

    seen_hashes: dict[str, Path] = {}
    skipped_duplicates: list[tuple[Path, Path]] = []
    skipped_empty: list[Path] = []
    failures: list[tuple[Path, str]] = []
    ingested: list[tuple[Path, int]] = []
    total_chunks = 0

    for path in files:
        rel = path.relative_to(REPO_ROOT)
        try:
            raw = path.read_bytes()
        except OSError as e:
            failures.append((path, f"读文件失败: {e}"))
            continue
        if not raw.strip():
            skipped_empty.append(path)
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen_hashes:
            skipped_duplicates.append((path, seen_hashes[digest]))
            continue
        seen_hashes[digest] = path

        try:
            nodes = get_nodes_from_file(str(path))
        except Exception as e:
            failures.append((path, f"解析失败: {type(e).__name__}: {e}"))
            continue
        if not nodes:
            skipped_empty.append(path)
            continue

        try:
            index.insert_nodes(nodes)
        except Exception as e:
            failures.append((path, f"插入失败: {type(e).__name__}: {e}"))
            continue

        ingested.append((path, len(nodes)))
        total_chunks += len(nodes)
        print(f"[ingest]   + {rel}  ({len(nodes)} chunks)")

    print()
    print("=" * 72)
    print(f"导入完成 -> collection {args.collection!r}")
    print(f"  导入文件数:   {len(ingested)}")
    print(f"  跳过重复数:   {len(skipped_duplicates)}")
    print(f"  跳过空文件数: {len(skipped_empty)}")
    print(f"  解析失败数:   {len(failures)}")
    print(f"  总 chunk 数:  {total_chunks}  (collection.count()={collection.count()})")
    print("=" * 72)

    if skipped_duplicates:
        print("\n跳过的重复文件（重复项 <- 已导入的同内容文件）:")
        for dup, kept in skipped_duplicates:
            print(f"  - {dup.relative_to(REPO_ROOT)}\n      <- {kept.relative_to(REPO_ROOT)}")
    if skipped_empty:
        print("\n跳过的空文件/无内容文件:")
        for p in skipped_empty:
            print(f"  - {p.relative_to(REPO_ROOT)}")
    if failures:
        print("\n解析/插入失败的文件:")
        for p, reason in failures:
            print(f"  - {p.relative_to(REPO_ROOT)}: {reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
