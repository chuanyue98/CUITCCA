import unittest
from unittest.mock import MagicMock, patch

from dependencies.index_dep import get_index
from fastapi.testclient import TestClient
from llama_index.core.schema import NodeWithScore, TextNode
from main import app

import tests._pathsetup  # noqa: F401


class _FakeResponse:
    response = "mock answer"

    def __str__(self) -> str:
        return self.response


class ResponseRouterTest(unittest.TestCase):
    """``/response/{index}/query`` 走的是"统一检索入口 + 可选合成策略"。

    这个端点以前直接调 ``index.as_query_engine()``，绕开了混合检索与条件重排
    ——同一个知识库、同一个问题，走 /graph 和走这里检索质量不一样，而且差异
    不体现在任何配置上。这组测试钉住"必须走 build_retriever_for_index"这个
    契约，防止以后又被改回去。
    """

    def setUp(self):
        self.fake_index = MagicMock()
        app.dependency_overrides[get_index] = lambda: self.fake_index
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def _post(self, response_mode: str, prompt_type: str, query: str):
        return self.client.post(
            "/response/test_index/query",
            data={"response_mode": response_mode, "prompt_type": prompt_type, "query": query},
        )

    @patch("router.response.RetrieverQueryEngine")
    @patch("router.response.build_retriever_for_index")
    @patch("router.response.get_prompt_by_name")
    @patch("router.response.get_response_synthesizer")
    def test_query_success_default_mode(self, mock_synth, mock_prompt, mock_build_retriever, mock_engine_cls):
        mock_prompt.return_value = "You are a helpful assistant."
        mock_synth.return_value = MagicMock()

        engine = MagicMock()

        async def _aquery(_query):
            return _FakeResponse()

        engine.aquery = _aquery
        mock_engine_cls.from_args.return_value = engine

        response = self._post("compact", "QA_PROMPT", "what is this?")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "mock answer"})
        mock_prompt.assert_called_once()
        mock_synth.assert_called_once_with(response_mode="compact")

    @patch("router.response.RetrieverQueryEngine")
    @patch("router.response.build_retriever_for_index")
    @patch("router.response.get_prompt_by_name")
    @patch("router.response.get_response_synthesizer")
    def test_uses_unified_retriever_entry_point(self, mock_synth, mock_prompt, mock_build_retriever, mock_engine_cls):
        """必须经 build_retriever_for_index，而不是 index.as_query_engine()。"""
        mock_prompt.return_value = "prompt"
        mock_synth.return_value = MagicMock()
        engine = MagicMock()

        async def _aquery(_query):
            return _FakeResponse()

        engine.aquery = _aquery
        mock_engine_cls.from_args.return_value = engine

        self._post("compact", "QA_PROMPT", "问题")

        mock_build_retriever.assert_called_once()
        self.fake_index.as_query_engine.assert_not_called()

        # 传给 QueryEngine 的必须是那个 retriever，并且挂上了条件重排后处理器
        kwargs = mock_engine_cls.from_args.call_args.kwargs
        self.assertIs(kwargs["retriever"], mock_build_retriever.return_value)
        self.assertEqual(len(kwargs["node_postprocessors"]), 1)

    @patch("router.response.RetrieverQueryEngine")
    @patch("router.response.build_retriever_for_index")
    @patch("router.response.get_prompt_by_name")
    @patch("router.response.get_response_synthesizer")
    def test_recall_is_widened_so_conditional_rerank_can_actually_fire(
        self, mock_synth, mock_prompt, mock_build_retriever, mock_engine_cls
    ):
        """召回宽度必须来自 ``resolve_effective_top_k``，不能直接用
        ``DEFAULT_SIMILARITY_TOP_K``。

        后者等于 ``RERANK_TOP_N``（都是 5），而 ``ConditionalRerankPostprocessor``
        在 ``len(nodes) <= RERANK_TOP_N`` 时直接跳过重排——只召回 5 条却挂一个
        重排后处理器，是一个永远不会触发的摆设。必须先宽召回
        （``RERANK_RECALL_K``=20）再重排截断到 5，条件触发才有意义。

        顺带这也保证了不会退回 /index 那条链路的 QUERY_ENDPOINT_TOP_K(=2)——
        那会把 tree_summarize/accumulate 这类 response_mode 的选择权架空。
        """
        import configs.load_env as load_env

        mock_prompt.return_value = "prompt"
        mock_synth.return_value = MagicMock()
        engine = MagicMock()

        async def _aquery(_query):
            return _FakeResponse()

        engine.aquery = _aquery
        mock_engine_cls.from_args.return_value = engine

        self._post("tree_summarize", "QA_PROMPT", "问题")

        _, top_k = mock_build_retriever.call_args.args
        self.assertGreater(
            top_k, load_env.RERANK_TOP_N,
            "召回数必须大于 RERANK_TOP_N，否则条件重排永远不会触发",
        )
        self.assertEqual(top_k, load_env.RERANK_RECALL_K)
        self.assertNotEqual(top_k, load_env.QUERY_ENDPOINT_TOP_K)

    @patch("router.response.RetrieverQueryEngine")
    @patch("router.response.build_retriever_for_index")
    @patch("router.response.get_prompt_by_name")
    @patch("router.response.get_response_synthesizer")
    def test_query_with_refine_and_condense(self, mock_synth, mock_prompt, mock_build_retriever, mock_engine_cls):
        mock_prompt.return_value = "Custom prompt template."
        mock_synth.return_value = MagicMock()
        engine = MagicMock()

        async def _aquery(_query):
            return _FakeResponse()

        engine.aquery = _aquery
        mock_engine_cls.from_args.return_value = engine

        response = self._post("refine", "CONDENSE_QUESTION_PROMPT", "another question")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "mock answer"})
        mock_synth.assert_called_once_with(response_mode="refine")


class ConditionalRerankWiringTest(unittest.TestCase):
    """挂上去的后处理器得真的是那一个，而不是随便一个对象。"""

    def test_postprocessor_is_the_conditional_reranker(self):
        from utils.rerank import ConditionalRerankPostprocessor

        pp = ConditionalRerankPostprocessor()
        nodes = [NodeWithScore(node=TextNode(text="x"), score=0.99)]
        # RERANK_ENABLED 打开且 top1 高于阈值时应直接截断返回，不触发 cross-encoder
        self.assertEqual(pp.postprocess_nodes(nodes, query_bundle=None), nodes)


if __name__ == "__main__":
    unittest.main()
