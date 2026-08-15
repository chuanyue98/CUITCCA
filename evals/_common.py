"""共享小工具：给 evals/ 下的脚本（generate_golden.py、run_retrieval_eval.py）复用。

不是业务代码，只是评测脚本之间避免复制粘贴的胶水代码。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
BACKEND_APP_DIR = REPO_ROOT / "backend" / "app"

# 上传文件被 ingest 时会自动加上一个 uuid4 前缀（见 backend/app/router/index.py
# 里生成 unique_id 的逻辑），例如 Chroma 里存的 file_name 是
# "2e436f4b-7a5e-4c2f-ad80-a038f9083783_学校招生就业处概况.txt"。
# golden 数据集里为了可读性和稳定性，只写原始文件名（不含 uuid 前缀）。
_UUID_PREFIX_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}_"
)


def bootstrap_backend_path() -> None:
    """把 backend/app 加进 sys.path，这样才能 `import configs.xxx` / `import handlers.xxx`。

    和 tests/_pathsetup.py 做的事情一样，独立复制一份是因为 evals/ 脚本要能在
    pytest 环境之外，作为独立命令行工具直接运行（`uv run python evals/xxx.py`）。
    """
    app_dir = str(BACKEND_APP_DIR)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)


def load_backend_env() -> None:
    """把 backend/.env 读进 os.environ，供"有没有配 LLM"这类前置检查使用。

    后端自己在 configs/load_env.py 里 load_dotenv(backend/.env)，但那要等到
    真的 import 配置模块才发生。评测脚本在 import 之前就要判断
    OPENAI_API_KEY 在不在，于是按 README 把 key 配在 backend/.env 里的人会被
    "没配置 OPENAI_API_KEY" 挡掉——明明配好了却跑不起来。这里先补上这一步。

    已经在 os.environ 里的值优先（override=False），CI 用 secrets 注入环境变量
    的方式因此不会被本地 .env 覆盖。
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # 没装 python-dotenv 就退化为只看环境变量
        return
    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)


async def load_indexes_or_fail(script: str) -> None:
    """把索引注册表加载起来，加载不出东西就直接报错退出。

    生成阶段的评测（拒答 / 回答质量）走的是 QAWorkflow，而 QAWorkflow 的
    ``_build_retriever()`` 读的是 handlers.index_crud 里的模块级 ``indexes``
    列表。这个列表由 ``loadAllIndexes()`` 填充，FastAPI 在启动时会调用它——
    但评测脚本是独立进程，不走 FastAPI 启动流程，之前谁都没调用过它。

    后果很隐蔽：``indexes`` 为空时 ``_build_retriever()`` 返回 ``_EmptyRetriever``，
    每道题都检索到 0 条内容，QAWorkflow 于是对所有问题都回兜底文案"我还不知道"。
    这时候拒答评测会给出满分（兜底文案含"不知道"，天然算承认边界，也永远不会
    命中禁止信号），回答质量评测则全线最低分——两个指标都是假的，而且脚本不会
    报任何错。2026-08-15 第一次归档基线时就踩了这个坑，结果作废。

    所以这里跟 run_retrieval_eval.py 的"collection 是空的就拒跑"守卫对齐：
    宁可明确失败，也不要产出一份看起来很漂亮的无效数据。
    """
    from handlers.index_crud import indexes, loadAllIndexes

    await loadAllIndexes()
    if not indexes:
        raise SystemExit(
            f"[{script}] 索引注册表是空的，没有可评测的知识库。\n"
            "  生成阶段的评测必须有真实索引，否则每道题都会回兜底文案，\n"
            "  指标看着漂亮但完全无效。请先确认 data/chroma_db 下有数据\n"
            "  （uv run python evals/ingest_corpus.py 可以导入语料）。"
        )
    print(f"[{script}] 已加载 {len(indexes)} 个索引: {[i.index_id for i in indexes]}", flush=True)


def strip_uuid_prefix(file_name: str) -> str:
    """去掉上传时自动加的 uuid4 前缀，还原成原始文件名。"""
    if not file_name:
        return file_name
    return _UUID_PREFIX_RE.sub("", file_name)


def source_matches(expected_source: str, metadata: dict) -> bool:
    """判断一个 node 的 metadata 是否命中某个 golden 条目里的 expected_source。

    以侦察到的实际 Chroma metadata 结构为准（见 backend/app/handlers/vector_store.py
    的 insert 路径 / SimpleDirectoryReader 产出的 metadata）：常见 key 有
    `file_name`（带 uuid 前缀）、`doc_id`、`ref_doc_id`（和 file_name 相同）。
    这里做宽松匹配：只要任意候选 metadata 值，去掉 uuid 前缀后与 expected_source
    完全相等，或互为子串，就算命中。
    """
    if not expected_source:
        return False
    expected_norm = strip_uuid_prefix(expected_source).strip()
    if not expected_norm:
        return False

    for key in ("file_name", "doc_id", "ref_doc_id", "source", "file_path"):
        raw_value = metadata.get(key)
        if not raw_value:
            continue
        # file_path 是绝对路径，只取文件名部分
        candidate = os.path.basename(str(raw_value))
        candidate_norm = strip_uuid_prefix(candidate).strip()
        if not candidate_norm:
            continue
        if candidate_norm == expected_norm:
            return True
        if expected_norm in candidate_norm or candidate_norm in expected_norm:
            return True
    return False


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no} 不是合法的 JSON: {e}") from e
    return records


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


GOLDEN_REQUIRED_FIELDS = ("id", "question", "expected_answer", "expected_sources", "category")


def first_hit_rank(expected_sources: list[str], nodes_with_scores) -> tuple[int | None, str | None]:
    """返回检索结果里第一个命中 expected_sources 的排名（1-based）和命中的来源。

    没命中返回 (None, None)。run_retrieval_eval.py 和 run_rerank_eval.py 共用。
    """
    for i, nws in enumerate(nodes_with_scores, start=1):
        metadata = nws.node.metadata or {}
        for expected in expected_sources:
            if source_matches(expected, metadata):
                return i, expected
    return None, None


def format_retrieved(nodes_with_scores) -> list[dict]:
    """把检索结果整理成可写进 JSON 报告的精简结构。"""
    return [
        {
            "rank": i,
            "file_name": (nws.node.metadata or {}).get("file_name")
            or (nws.node.metadata or {}).get("doc_id")
            or "",
            "score": float(nws.score) if nws.score is not None else None,
        }
        for i, nws in enumerate(nodes_with_scores, start=1)
    ]


def hit_rate_at(ranks: list[int | None], k: int) -> float:
    """hit_rate@k：first-hit 排名 <= k 的比例。ranks 里 None 表示未命中。"""
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def mrr_at(ranks: list[int | None], k: int) -> float:
    """MRR@k：first-hit 排名 <= k 时计 1/rank，否则计 0，再取平均。"""
    if not ranks:
        return 0.0
    return sum(1.0 / r for r in ranks if r is not None and r <= k) / len(ranks)
