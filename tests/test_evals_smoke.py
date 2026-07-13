"""冒烟测试：只检查 evals/ 骨架本身是不是完好的，不跑任何真实检索/生成评测。

- golden.seed.jsonl 每行能被解析成合法 JSON，必填字段齐全，id 不重复。
- evals 包里的脚本模块能被正常 import（不触发 argparse/网络请求/LLM 调用，
  因为脚本入口都写在 `if __name__ == "__main__":` 里）。

真实的检索评测（需要本地 Chroma 索引数据）由 evals/run_retrieval_eval.py
在本地/服务器手动跑，见 evals/README.md；不放进默认 pytest 套件里跑。
"""
import json
import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GOLDEN_PATH = os.path.join(_REPO_ROOT, "evals", "golden.seed.jsonl")

_REQUIRED_FIELDS = ("id", "question", "expected_answer", "expected_sources", "category")


def _load_golden_lines():
    with open(_GOLDEN_PATH, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines


@pytest.fixture(scope="module")
def golden_records():
    records = []
    for line_no, line in enumerate(_load_golden_lines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            pytest.fail(f"evals/golden.seed.jsonl 第 {line_no} 行不是合法 JSON: {e}")
        records.append(record)
    return records


def test_golden_seed_file_exists():
    assert os.path.isfile(_GOLDEN_PATH), "evals/golden.seed.jsonl 不存在"


def test_golden_seed_is_not_empty(golden_records):
    assert len(golden_records) >= 5, "golden.seed.jsonl 至少应该有几条种子数据"


def test_golden_seed_every_line_has_required_fields(golden_records):
    for record in golden_records:
        missing = [field for field in _REQUIRED_FIELDS if field not in record]
        assert not missing, f"记录 {record.get('id', '?')} 缺少字段: {missing}"


def test_golden_seed_field_types_and_non_empty(golden_records):
    for record in golden_records:
        assert isinstance(record["id"], str) and record["id"], f"{record}: id 必须是非空字符串"
        assert isinstance(record["question"], str) and record["question"].strip(), (
            f"{record['id']}: question 不能为空"
        )
        assert isinstance(record["expected_answer"], str) and record["expected_answer"].strip(), (
            f"{record['id']}: expected_answer 不能为空"
        )
        assert isinstance(record["expected_sources"], list) and record["expected_sources"], (
            f"{record['id']}: expected_sources 必须是非空列表"
        )
        assert all(isinstance(s, str) and s.strip() for s in record["expected_sources"]), (
            f"{record['id']}: expected_sources 里的每一项都必须是非空字符串"
        )
        assert isinstance(record["category"], str) and record["category"].strip(), (
            f"{record['id']}: category 不能为空"
        )


def test_golden_seed_ids_are_unique(golden_records):
    ids = [record["id"] for record in golden_records]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"golden.seed.jsonl 里有重复的 id: {duplicates}"


def test_run_retrieval_eval_module_imports_without_side_effects():
    """脚本入口在 `if __name__ == '__main__':` 里，import 不应该触发任何真实评测、
    网络请求或 argparse 解析。"""
    import evals.run_retrieval_eval as run_retrieval_eval

    assert callable(run_retrieval_eval.main)
    assert callable(run_retrieval_eval.run_eval)
    assert run_retrieval_eval.DEFAULT_TOP_K == 5


def test_generate_golden_module_imports_without_side_effects():
    import evals.generate_golden as generate_golden

    assert callable(generate_golden.main)


def test_ingest_corpus_module_imports_without_side_effects():
    import evals.ingest_corpus as ingest_corpus

    assert callable(ingest_corpus.main)
    assert ingest_corpus.DEFAULT_COLLECTION == "campus-corpus"


def test_common_module_strip_uuid_prefix():
    from evals._common import strip_uuid_prefix

    uuid_prefixed = "2e436f4b-7a5e-4c2f-ad80-a038f9083783_学校招生就业处概况.txt"
    assert strip_uuid_prefix(uuid_prefixed) == "学校招生就业处概况.txt"
    assert strip_uuid_prefix("plain_name.txt") == "plain_name.txt"


def test_common_module_source_matches():
    from evals._common import source_matches

    # test-index 风格：file_name 带线上上传路径加的 uuid 前缀
    metadata = {"file_name": "2e436f4b-7a5e-4c2f-ad80-a038f9083783_学校招生就业处概况.txt"}
    assert source_matches("学校招生就业处概况.txt", metadata) is True
    assert source_matches("完全不相关的文件.txt", metadata) is False

    # campus-corpus 风格（evals/ingest_corpus.py 导入）：file_name 就是原始文件名
    plain_metadata = {"file_name": "学校历史.txt"}
    assert source_matches("学校历史.txt", plain_metadata) is True
    assert source_matches("学校简介.txt", plain_metadata) is False
    # 名字相近但不构成子串的文件不能误判命中
    assert source_matches("食堂.txt", {"file_name": "食堂投诉电话及投诉程序.txt"}) is False
