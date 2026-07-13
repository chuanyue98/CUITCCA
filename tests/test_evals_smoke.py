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


def test_run_rerank_eval_module_imports_without_side_effects():
    """import 不应触发模型下载/加载（sentence-transformers 只在函数体内 import）。"""
    import evals.run_rerank_eval as run_rerank_eval

    assert callable(run_rerank_eval.main)
    assert callable(run_rerank_eval.run_ab_eval)
    assert run_rerank_eval.DEFAULT_TOP_K == 5
    assert run_rerank_eval.DEFAULT_RECALL_K == 20


def test_common_rank_metric_helpers():
    from evals._common import hit_rate_at, mrr_at

    ranks = [1, 3, None, 2]
    assert hit_rate_at(ranks, 1) == 0.25
    assert hit_rate_at(ranks, 2) == 0.5
    assert hit_rate_at(ranks, 5) == 0.75
    assert mrr_at(ranks, 5) == (1.0 + 1 / 3 + 0.0 + 0.5) / 4
    assert mrr_at(ranks, 2) == (1.0 + 0.0 + 0.0 + 0.5) / 4
    assert hit_rate_at([], 5) == 0.0
    assert mrr_at([], 5) == 0.0


def test_common_module_strip_uuid_prefix():
    from evals._common import strip_uuid_prefix

    uuid_prefixed = "2e436f4b-7a5e-4c2f-ad80-a038f9083783_学校招生就业处概况.txt"
    assert strip_uuid_prefix(uuid_prefixed) == "学校招生就业处概况.txt"
    assert strip_uuid_prefix("plain_name.txt") == "plain_name.txt"


def test_run_retrieval_eval_overall_metrics_match_shared_helpers():
    """Fix #8 回归测试：run_retrieval_eval.py 里 overall hit_rate/mrr 现在用
    evals._common.hit_rate_at/mrr_at 计算，而不是手写的逐条累加公式。每条
    detail 的 retrieved 已经被截断到 top_k（rank 非 None 时恒 <= top_k），
    所以两种算法在数值上应该完全等价——这里直接对比两种算法而不依赖本地
    Chroma 索引数据（CI/沙箱环境通常没有）。"""
    from evals._common import hit_rate_at, mrr_at

    ranks = [1, None, 3, 2]
    top_k = 5

    details = [{"hit": r is not None, "reciprocal_rank": (1.0 / r if r is not None else 0.0)} for r in ranks]
    manual_hit_rate = sum(d["hit"] for d in details) / len(details) if details else 0.0
    manual_mrr = sum(d["reciprocal_rank"] for d in details) / len(details) if details else 0.0

    assert hit_rate_at(ranks, top_k) == manual_hit_rate
    assert mrr_at(ranks, top_k) == manual_mrr


def test_run_retrieval_eval_module_actually_wires_the_shared_helpers():
    import inspect

    import evals.run_retrieval_eval as run_retrieval_eval

    source = inspect.getsource(run_retrieval_eval)
    assert "hit_rate_at" in source
    assert "mrr_at" in source


def test_run_rerank_eval_prints_diagnostic_when_collection_count_raises(capsys):
    """Fix #10 回归测试：collection.count() 抛异常时，run_ab_eval 应该走和
    "空 collection" 一样的诊断输出路径（打印 "是空的" 提示后返回 None），
    而不是静默返回 None、什么都不打印——那样和真正的空跑成功没法区分。"""
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    import evals.run_rerank_eval as run_rerank_eval

    fake_collection = MagicMock()
    fake_collection.count.side_effect = RuntimeError("boom")

    with patch("evals.run_retrieval_eval._detect_collection", return_value="campus-corpus"), \
            patch("handlers.vector_store.get_or_create_collection", return_value=fake_collection):
        result = run_rerank_eval.run_ab_eval(
            golden_path=Path("/nonexistent/does-not-matter.jsonl"),
            collection_name=None,
            top_k=5,
            recall_k=20,
            reranker_model="BAAI/bge-reranker-v2-m3",
        )

    assert result is None
    captured = capsys.readouterr()
    assert "是空的" in captured.out
    assert "campus-corpus" in captured.out


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
