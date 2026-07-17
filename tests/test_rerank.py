"""backend/app/utils/rerank.py 的测试。

覆盖 ConditionalRerankPostprocessor._postprocess_nodes 的全部分支：
1. RERANK_ENABLED=False（默认值）时直接截断到 RERANK_TOP_N，不触发任何 rerank
   逻辑、不加载/不 import SentenceTransformerRerank。
2. RERANK_ENABLED=True 且传入空 nodes 列表 -> 原样返回空列表。
3. RERANK_ENABLED=True，top1 分数 >= RERANK_SCORE_THRESHOLD -> 跳过 rerank，
   直接截断到 RERANK_TOP_N。
4. RERANK_ENABLED=True，len(nodes) <= RERANK_TOP_N -> 跳过 rerank（即使 top1
   分数低于阈值），原样返回全部 nodes。
5. RERANK_ENABLED=True，top1 分数 < 阈值 且 len(nodes) > RERANK_TOP_N -> 触发
   rerank：mock 掉 _get_reranker，断言调用了 mock reranker 的
   postprocess_nodes，且返回值就是 mock 的返回值。

额外覆盖 _get_reranker() 的懒加载 + 缓存逻辑（mock 掉 SentenceTransformerRerank
本身，绝不真的实例化/下载模型）。

全程通过 monkeypatch 改 configs.load_env 的模块属性（该模块用
`import configs.load_env as load_env` + `load_env.XXX` 的方式读取配置，不是
`from configs.load_env import XXX`），测试结束后 monkeypatch fixture 会自动
还原，不需要手动改回去。
"""
from unittest.mock import MagicMock, patch

import configs.load_env as load_env
import utils.rerank as rerank_module
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


def _make_node(text: str, score: float) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=text), score=score)


def test_disabled_returns_truncated_nodes_without_touching_reranker(monkeypatch):
    monkeypatch.setattr(load_env, "RERANK_ENABLED", False)
    monkeypatch.setattr(load_env, "RERANK_TOP_N", 3)
    nodes = [_make_node(f"n{i}", 1.0 - i * 0.1) for i in range(8)]

    with patch.object(rerank_module, "_get_reranker") as mock_get_reranker:
        result = rerank_module.ConditionalRerankPostprocessor().postprocess_nodes(nodes)

    assert result == nodes[:3]
    mock_get_reranker.assert_not_called()


def test_enabled_with_empty_nodes_returns_empty_list(monkeypatch):
    monkeypatch.setattr(load_env, "RERANK_ENABLED", True)

    result = rerank_module.ConditionalRerankPostprocessor().postprocess_nodes([])

    assert result == []


def test_enabled_top1_above_threshold_skips_rerank(monkeypatch):
    monkeypatch.setattr(load_env, "RERANK_ENABLED", True)
    monkeypatch.setattr(load_env, "RERANK_SCORE_THRESHOLD", 0.75)
    monkeypatch.setattr(load_env, "RERANK_TOP_N", 3)
    nodes = [
        _make_node(f"n{i}", score)
        for i, score in enumerate([0.9, 0.6, 0.5, 0.4, 0.3, 0.2])
    ]

    with patch.object(rerank_module, "_get_reranker") as mock_get_reranker:
        result = rerank_module.ConditionalRerankPostprocessor().postprocess_nodes(nodes)

    assert result == nodes[:3]
    mock_get_reranker.assert_not_called()


def test_enabled_recall_not_exceeding_top_n_skips_rerank_even_with_low_score(monkeypatch):
    monkeypatch.setattr(load_env, "RERANK_ENABLED", True)
    monkeypatch.setattr(load_env, "RERANK_SCORE_THRESHOLD", 0.75)
    monkeypatch.setattr(load_env, "RERANK_TOP_N", 5)
    # top1 分数远低于阈值，但节点总数(3) <= RERANK_TOP_N(5)，仍应跳过 rerank。
    nodes = [_make_node(f"n{i}", score) for i, score in enumerate([0.3, 0.2, 0.1])]

    with patch.object(rerank_module, "_get_reranker") as mock_get_reranker:
        result = rerank_module.ConditionalRerankPostprocessor().postprocess_nodes(nodes)

    assert result == nodes
    mock_get_reranker.assert_not_called()


def test_enabled_low_top1_and_excess_recall_triggers_rerank(monkeypatch):
    monkeypatch.setattr(load_env, "RERANK_ENABLED", True)
    monkeypatch.setattr(load_env, "RERANK_SCORE_THRESHOLD", 0.75)
    monkeypatch.setattr(load_env, "RERANK_TOP_N", 3)
    nodes = [
        _make_node(f"n{i}", score)
        for i, score in enumerate([0.3, 0.25, 0.2, 0.15, 0.1])
    ]
    reranked_sentinel = [nodes[2], nodes[0]]

    mock_reranker = MagicMock()
    mock_reranker.postprocess_nodes.return_value = reranked_sentinel

    with patch.object(
        rerank_module, "_get_reranker", return_value=mock_reranker
    ) as mock_get_reranker:
        query_bundle = QueryBundle("测试查询")
        result = rerank_module.ConditionalRerankPostprocessor().postprocess_nodes(
            nodes, query_bundle=query_bundle
        )

    mock_get_reranker.assert_called_once()
    mock_reranker.postprocess_nodes.assert_called_once_with(
        nodes, query_bundle=query_bundle
    )
    assert result is reranked_sentinel


def test_enabled_trigger_rerank_without_query_bundle_builds_empty_query_str(monkeypatch):
    """query_bundle=None 时应构造一个空字符串的 QueryBundle 传给 reranker，而不是崩溃。"""
    monkeypatch.setattr(load_env, "RERANK_ENABLED", True)
    monkeypatch.setattr(load_env, "RERANK_SCORE_THRESHOLD", 0.75)
    monkeypatch.setattr(load_env, "RERANK_TOP_N", 2)
    nodes = [_make_node(f"n{i}", score) for i, score in enumerate([0.3, 0.25, 0.2])]

    mock_reranker = MagicMock()
    mock_reranker.postprocess_nodes.return_value = nodes[:2]

    with patch.object(rerank_module, "_get_reranker", return_value=mock_reranker):
        result = rerank_module.ConditionalRerankPostprocessor().postprocess_nodes(nodes)

    called_args, called_kwargs = mock_reranker.postprocess_nodes.call_args
    assert called_args[0] == nodes
    assert called_kwargs["query_bundle"].query_str == ""
    assert result == nodes[:2]


def test_get_reranker_lazily_constructs_and_caches_instance(monkeypatch):
    # _reranker_instance 是模块级单例缓存，测试前后都强制置空，避免和其它测试/
    # 真实运行互相污染；monkeypatch 保证测试结束后自动还原成 patch 前的值。
    monkeypatch.setattr(rerank_module, "_reranker_instance", None)
    monkeypatch.setattr(load_env, "RERANKER_MODEL", "fake/model")
    monkeypatch.setattr(load_env, "RERANK_TOP_N", 4)

    fake_reranker = MagicMock()
    with patch(
        "llama_index.core.postprocessor.SentenceTransformerRerank",
        return_value=fake_reranker,
    ) as mock_cls:
        first = rerank_module._get_reranker()
        second = rerank_module._get_reranker()

    mock_cls.assert_called_once_with(model="fake/model", top_n=4)
    assert first is fake_reranker
    assert second is fake_reranker
