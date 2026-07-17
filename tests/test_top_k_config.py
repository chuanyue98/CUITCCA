"""检索 top_k 集中配置（Phase 2）的测试。

三个常量集中定义在 configs/load_env.py，可通过同名环境变量覆盖，默认值
必须和改造前各调用点原来硬编码的值完全一致（5 / 2 / 3），否则就是悄悄改变
了线上行为。风格参考 tests/test_cookie_config.py。
"""
import os
import unittest
from unittest.mock import MagicMock, patch

import tests._pathsetup  # noqa: F401


class TopKConfigDefaultsTest(unittest.TestCase):
    def test_defaults_match_pre_refactor_hardcoded_values(self):
        env = dict(os.environ)
        for key in ('SIMILARITY_TOP_K', 'QUERY_ENDPOINT_TOP_K', 'MULTI_INDEX_FALLBACK_TOP_K'):
            env.pop(key, None)
        with patch.dict(os.environ, env, clear=True):
            import importlib

            import configs.load_env as env_mod
            importlib.reload(env_mod)

            self.assertEqual(env_mod.DEFAULT_SIMILARITY_TOP_K, 5)
            self.assertEqual(env_mod.QUERY_ENDPOINT_TOP_K, 2)
            self.assertEqual(env_mod.MULTI_INDEX_FALLBACK_TOP_K, 3)

    def test_each_constant_overridable_via_its_own_env_var(self):
        with patch.dict(
            os.environ,
            {
                'SIMILARITY_TOP_K': '7',
                'QUERY_ENDPOINT_TOP_K': '4',
                'MULTI_INDEX_FALLBACK_TOP_K': '9',
            },
        ):
            import importlib

            import configs.load_env as env_mod
            importlib.reload(env_mod)

            self.assertEqual(env_mod.DEFAULT_SIMILARITY_TOP_K, 7)
            self.assertEqual(env_mod.QUERY_ENDPOINT_TOP_K, 4)
            self.assertEqual(env_mod.MULTI_INDEX_FALLBACK_TOP_K, 9)

        # 复原，避免污染后续测试（模块级全局状态）
        import importlib

        import configs.load_env as env_mod
        importlib.reload(env_mod)


class TopKConfigWiringTest(unittest.TestCase):
    """确认调用点确实在读这些常量，而不是又悄悄换回字面量。

    graph_builder.py 原来的 _build_query_engine/MultiIndexQueryEngine（用到
    DEFAULT_SIMILARITY_TOP_K/MULTI_INDEX_FALLBACK_TOP_K 的地方）已经在切换到
    QAWorkflow 时删除，graph_builder.py 现在只剩 summary_index()，不再是
    top_k 配置的接线点——对应的 wiring 检查已经并入下面
    test_qa_workflow_imports_the_shared_constant（qa_workflow._build_retriever
    是现在唯一的检索 top_k 接线点）。
    """

    def test_query_endpoint_imports_the_shared_constant(self):
        import inspect

        import router.index as index_router

        source = inspect.getsource(index_router)
        self.assertIn('QUERY_ENDPOINT_TOP_K', source)
        self.assertNotIn('similarity_top_k=2', source)

    def test_qa_workflow_imports_the_shared_constant(self):
        import inspect

        import handlers.qa_workflow as qa_workflow

        source = inspect.getsource(qa_workflow)
        self.assertIn('load_env.DEFAULT_SIMILARITY_TOP_K', source)
        self.assertNotIn('similarity_top_k=5', source)

    def test_qa_workflow_build_retriever_reads_live_value_after_reload(self):
        """更直接的回归测试：修改 SIMILARITY_TOP_K 环境变量、reload
        configs.load_env 之后，qa_workflow._build_retriever() 应该读到新值，
        而不是 `from configs.load_env import DEFAULT_SIMILARITY_TOP_K` 在模块
        导入时就拷贝死的旧值——这正是 qa_workflow.py 里 Fix #2 要修的坑。"""
        import importlib

        import configs.load_env as env_mod
        import handlers.qa_workflow as qa_workflow

        with patch.dict(os.environ, {'SIMILARITY_TOP_K': '11'}):
            importlib.reload(env_mod)
            try:
                fake_index = MagicMock()
                fake_index.index_id = 'idx1'
                fake_retriever = MagicMock()
                fake_index.as_retriever.return_value = fake_retriever

                with patch.object(qa_workflow, 'indexes', [fake_index]):
                    result = qa_workflow._build_retriever()

                fake_index.as_retriever.assert_called_once_with(similarity_top_k=11)
                assert result is fake_retriever
            finally:
                # 复原，避免污染后续测试（模块级全局状态）
                importlib.reload(env_mod)


if __name__ == '__main__':
    unittest.main()
