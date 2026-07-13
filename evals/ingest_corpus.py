#!/usr/bin/env python
"""一次性导入脚本：把仓库里未被索引的真实文档全量导入 Chroma collection `campus-corpus`。

服务于评测基线（Phase 0/2），不是线上功能。直接调用
``backend/app/handlers/ingestion_pipeline.py`` 的唯一批量摄取入口
``ingest_files()``（不再自己手写一遍"消解冲突 -> 解析 -> pipeline.run"的
流程），保证评测语料的去重规则和"以后要不要把增量摄取接入线上"用的是同一套
代码：

- 文档 id = 内容 sha256（``content_hash``），metadata 的 ``file_name`` 默认是
  原始文件名（不含 uuid 前缀），``last_updated`` 是文件 mtime 对应的 ISO 日期。
- 同名冲突分两种：同一目录下的不同版本按 mtime 取更新版本（旧版本记录进
  conflicts 并打印，不静默丢弃）；不同目录下恰好同名但内容不同的文件，
  无法判断谁新谁旧，全部保留、用相对路径区分身份。
- 用 ``llama_index.core.ingestion.IngestionPipeline``（DocstoreStrategy.UPSERTS）
  实际做切块+嵌入+写入 Chroma；同一次运行内容完全相同但文件名不同的文档，
  会被 pipeline 按内容 hash 自动去重、只嵌入一次——这种情况下报告里会把
  所有共享同一份内容的文件名都列出来，不会因为"一个 doc_id 只能映射一个
  路径"这种简化模型而悄悄丢失其中一个文件名。

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
    from handlers.ingestion_pipeline import build_pipeline, ingest_files
    from handlers.vector_store import delete_collection, get_or_create_collection, list_index_names
    from llama_index.core.storage.docstore import SimpleDocumentStore
    from llama_index.vector_stores.chroma import ChromaVectorStore

    files = _collect_files(SOURCE_DIRS, {ext.lower() for ext in ALLOWED_EXTENSIONS})
    if not files:
        print("[ingest] 两个数据源目录下没有任何可解析文件，退出。")
        return 1
    print(f"[ingest] 发现 {len(files)} 个候选文件（扩展名过滤: {sorted(ALLOWED_EXTENSIONS)}）")

    # 重建 collection，保证可重复运行（全量对齐，不是增量）
    if args.collection in list_index_names():
        print(f"[ingest] collection {args.collection!r} 已存在，删除重建。")
        delete_collection(args.collection)
    collection = get_or_create_collection(args.collection)

    init_settings()
    vector_store = ChromaVectorStore(chroma_collection=collection)
    pipeline = build_pipeline(vector_store=vector_store, docstore=SimpleDocumentStore())

    print("[ingest] 开始摄取（消解同名冲突 -> 解析 -> 切块 -> 嵌入 -> 写入 Chroma）...")
    result = ingest_files(files, pipeline, corpus_root=REPO_ROOT)

    if result.unreadable_files:
        print("\n读取失败、已从所有去重判断中剔除的文件:")
        for p, reason in result.unreadable_files:
            print(f"  - {p.relative_to(REPO_ROOT)}: {reason}")

    if result.conflicts:
        print("\n发现的同名冲突:")
        for conflict in result.conflicts:
            print(f"  - {conflict.describe()}")

    # 按 doc_id 打印每份内容贡献的 chunk 数。一个 doc_id 对应多个文件名时
    # （不同名字、内容恰好完全相同）全部列出来，不会像单值 dict 那样后写入
    # 覆盖先写入、悄悄丢失其中一个文件名。
    for doc_id, paths in sorted(result.doc_id_to_paths.items(), key=lambda kv: str(sorted(kv[1])[0])):
        count = result.nodes_by_doc_id.get(doc_id, 0)
        names = " / ".join(str(p.relative_to(REPO_ROOT)) for p in sorted(paths))
        print(f"[ingest]   + {names}  ({count} chunks)")

    total_files_kept = sum(len(paths) for paths in result.doc_id_to_paths.values())
    cross_name_content_dupes = total_files_kept - len(result.doc_id_to_paths)

    print()
    print("=" * 72)
    print(f"导入完成 -> collection {args.collection!r}")
    print(f"  候选文件数:           {result.candidate_files}")
    print(f"  导入文件数:           {total_files_kept}")
    if cross_name_content_dupes:
        print(f"    其中跨文件名内容重复（同一 doc_id 多个文件名）: {cross_name_content_dupes}")
    print(f"  读取失败数:           {len(result.unreadable_files)}")
    print(f"  同名冲突组数:         {len(result.conflicts)}（明细见上）")
    print(f"  跳过空文件数:         {len(result.empty_files)}")
    print(f"  解析失败数:           {len(result.parse_failures)}")
    print(f"  总 chunk 数:          {result.nodes_upserted}  (collection.count()={collection.count()})")
    print("=" * 72)

    if result.empty_files:
        print("\n跳过的空文件/无内容文件:")
        for p in result.empty_files:
            print(f"  - {p.relative_to(REPO_ROOT)}")
    if result.parse_failures:
        print("\n解析失败的文件:")
        for p, reason in result.parse_failures:
            print(f"  - {p.relative_to(REPO_ROOT)}: {reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
