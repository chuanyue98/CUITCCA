"""检索 top_k 集中配置（Phase 2）的测试。

三个常量集中定义在 configs/load_env.py，可通过同名环境变量覆盖，默认值
必须和改造前各调用点原来硬编码的值完全一致（5 / 2 / 3），否则就是悄悄改变
了线上行为。风格参考 tests/test_cookie_config.py。
"""
import os
import unittest
from unittest.mock import patch

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
    """确认三个调用点确实在读这三个常量，而不是又悄悄换回字面量。"""

    def test_graph_builder_imports_the_shared_constants(self):
        import inspect

        import handlers.graph_builder as gb

        source = inspect.getsource(gb)
        self.assertIn('DEFAULT_SIMILARITY_TOP_K', source)
        self.assertIn('MULTI_INDEX_FALLBACK_TOP_K', source)
        self.assertNotIn('similarity_top_k=5', source)
        self.assertNotIn('similarity_top_k=3', source)

    def test_query_endpoint_imports_the_shared_constant(self):
        import inspect

        import router.index as index_router

        source = inspect.getsource(index_router)
        self.assertIn('QUERY_ENDPOINT_TOP_K', source)
        self.assertNotIn('similarity_top_k=2', source)


if __name__ == '__main__':
    unittest.main()
