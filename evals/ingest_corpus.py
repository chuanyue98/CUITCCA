#!/usr/bin/env python
"""一次性导入脚本：把仓库里未被索引的真实文档全量导入 Chroma collection `campus-corpus`。

服务于评测基线（Phase 0/2），不是线上功能。Phase 2 起复用
``backend/app/handlers/ingestion_pipeline.py`` 里的生产级去重/摄取逻辑（而不
是自己再写一套），保证评测语料的去重规则和"以后要不要把增量摄取接入线上"
用的是同一套代码：

- 文档 id = 内容 sha256（``content_hash``），metadata 的 ``file_name`` 是原始
  文件名（不含 uuid 前缀），``last_updated`` 是文件 mtime 对应的 ISO 日期。
- 同名不同内容冲突（比如两个版本的 学校历史.txt）按 mtime 取更新版本，旧版本
  记录进 conflicts 并打印，不静默丢弃。
- 用 ``llama_index.core.ingestion.IngestionPipeline``（DocstoreStrategy.UPSERTS）
  实际做切块+嵌入+写入 Chroma；同一次运行内容完全相同的文档（哪怕来自不同
  文件名/不同目录）会被 pipeline 按内容 hash 自动去重，不重复嵌入。

可重复运行：每次先删掉重建 `campus-corpus` collection、用一个全新的内存态
docstore，所以是"全量重新对齐当前语料状态"，不是增量运行（增量/持久化
docstore 的用法见 ingestion_pipeline.py 的 docstring）。

用法:
    uv run python evals/ingest_corpus.py
    uv run python evals/ingest_corpus.py --collection campus-corpus
"""
from __future__ import annotations

import argparse
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
    from handlers.ingestion_pipeline import build_pipeline, documents_from_file, resolve_authoritative_files
    from handlers.vector_store import delete_collection, get_or_create_collection, list_index_names
    from llama_index.core.storage.docstore import SimpleDocumentStore
    from llama_index.vector_stores.chroma import ChromaVectorStore

    files = _collect_files(SOURCE_DIRS, {ext.lower() for ext in ALLOWED_EXTENSIONS})
    if not files:
        print("[ingest] 两个数据源目录下没有任何可解析文件，退出。")
        return 1
    print(f"[ingest] 发现 {len(files)} 个候选文件（扩展名过滤: {sorted(ALLOWED_EXTENSIONS)}）")

    resolved_files, conflicts = resolve_authoritative_files(files)
    trivial_duplicates_collapsed = len(files) - len(resolved_files) - sum(len(c.discarded) for c in conflicts)
    print(
        f"[ingest] 同名分组消解后剩 {len(resolved_files)} 个权威文件"
        f"（合并纯重复 {trivial_duplicates_collapsed} 个，同名冲突 {len(conflicts)} 组）"
    )
    if conflicts:
        print("\n发现的同名不同内容冲突:")
        for conflict in conflicts:
            print(f"  - {conflict.describe()}")
        print()

    # 重建 collection，保证可重复运行（全量对齐，不是增量）
    if args.collection in list_index_names():
        print(f"[ingest] collection {args.collection!r} 已存在，删除重建。")
        delete_collection(args.collection)
    collection = get_or_create_collection(args.collection)

    init_settings()
    vector_store = ChromaVectorStore(chroma_collection=collection)
    pipeline = build_pipeline(vector_store=vector_store, docstore=SimpleDocumentStore())

    skipped_empty: list[Path] = []
    failures: list[tuple[Path, str]] = []
    documents = []
    doc_id_to_path: dict[str, Path] = {}

    for path in resolved_files:
        try:
            docs = documents_from_file(path)
        except Exception as e:
            failures.append((path, f"解析失败: {type(e).__name__}: {e}"))
            continue
        docs = [d for d in docs if d.get_content().strip()]
        if not docs:
            skipped_empty.append(path)
            continue
        for doc in docs:
            doc_id_to_path[doc.doc_id] = path
        documents.extend(docs)

    print(f"[ingest] 解析出 {len(documents)} 个 Document，开始摄取（切块+嵌入+写入 Chroma）...")
    try:
        nodes = pipeline.run(documents=documents) if documents else []
    except Exception as e:
        print(f"[ingest] 摄取过程中出错: {type(e).__name__}: {e}")
        return 1

    chunks_per_file: dict[Path, int] = {}
    for node in nodes:
        path = doc_id_to_path.get(node.ref_doc_id)
        if path is not None:
            chunks_per_file[path] = chunks_per_file.get(path, 0) + 1
    for path, count in sorted(chunks_per_file.items()):
        print(f"[ingest]   + {path.relative_to(REPO_ROOT)}  ({count} chunks)")

    print()
    print("=" * 72)
    print(f"导入完成 -> collection {args.collection!r}")
    print(f"  导入文件数:     {len(chunks_per_file)}")
    print(f"  跳过重复文件数: {trivial_duplicates_collapsed}")
    print(f"  同名冲突组数:   {len(conflicts)}（已按 mtime 取权威版本，明细见上）")
    print(f"  跳过空文件数:   {len(skipped_empty)}")
    print(f"  解析失败数:     {len(failures)}")
    print(f"  总 chunk 数:    {len(nodes)}  (collection.count()={collection.count()})")
    print("=" * 72)

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
