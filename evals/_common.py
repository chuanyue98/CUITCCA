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
