"""一次性把 信息搜集汇总/ 里的文件导入为一个线上可查询的索引。

使用流程:
    uv run python scripts/ingest_cori_online.py
    uv run python scripts/ingest_cori_online.py --index-name campus
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_APP_DIR = _REPO_ROOT / "backend" / "app"
if str(BACKEND_APP_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP_DIR))

from configs.llm_predictor import init_settings  # noqa: E402
from configs.load_env import ALLOWED_EXTENSIONS  # noqa: E402
from handlers.graph_builder import summary_index  # noqa: E402
from handlers.index_crud import (  # noqa: E402
    createIndex,
    get_index_by_name,
    insert_into_index,
    loadAllIndexes,
)


def collect_files(source_dir: Path, allowed_extensions: set[str]) -> list[Path]:
    if not source_dir.is_dir():
        print(f"[ingest] 目录不存在，跳过: {source_dir}")
        return []
    return sorted(
        p for p in source_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in allowed_extensions
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description="将 信息搜集汇总/ 导入为线上索引")
    parser.add_argument(
        "--index-name", default="campus",
        help="目标索引名称（默认 campus）",
    )
    parser.add_argument(
        "--source-dir", default="信息搜集汇总",
        help="语料源目录（默认 信息搜集汇总）",
    )
    args = parser.parse_args()

    index_name = args.index_name
    source_dir = _REPO_ROOT / args.source_dir

    files = collect_files(source_dir, {ext.lower() for ext in ALLOWED_EXTENSIONS})
    if not files:
        print("[ingest] 没有找到可导入的文件。")
        return 1

    print(f"[ingest] 找到 {len(files)} 个文件，目标索引: {index_name}")

    # 初始化 LLM / Embedding 配置
    init_settings()

    # 创建索引
    createIndex(index_name)
    print(f"[ingest] 索引 {index_name!r} 已创建")

    # 获取 index 对象
    index = get_index_by_name(index_name)
    if index is None:
        await loadAllIndexes()
        index = get_index_by_name(index_name)
    if index is None:
        print("[ingest] 无法获取索引对象，退出。")
        return 1

    # 逐个插入（skip_summary 避免 N+1 LLM 调用，最后统一生成）
    errors: list[tuple[Path, str]] = []
    for i, fp in enumerate(files, 1):
        try:
            await insert_into_index(index, str(fp), skip_summary=True)
            print(f"[ingest] ({i}/{len(files)}) ✓ {fp.relative_to(_REPO_ROOT)}")
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            errors.append((fp, err_msg))
            print(f"[ingest] ({i}/{len(files)}) ✗ {fp.relative_to(_REPO_ROOT)}: {err_msg}")

    # 统一生成摘要
    print("[ingest] 正在生成索引摘要...")
    try:
        index.summary = await summary_index(index)
        from handlers.index_crud import _save_summary
        _save_summary(index)
        print(f"[ingest] 摘要已生成: {index.summary[:120]}...")
    except Exception as e:
        print(f"[ingest] 摘要生成失败: {e}")

    print(f"\n[ingest] 导入完成 -> 索引 {index_name!r}")
    print(f"  成功: {len(files) - len(errors)}")
    print(f"  失败: {len(errors)}")
    if errors:
        for fp, err in errors:
            print(f"    - {fp.relative_to(_REPO_ROOT)}: {err}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
