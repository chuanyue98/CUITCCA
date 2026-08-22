import os
import unittest
from unittest.mock import patch

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


class CookieConfigTest(unittest.TestCase):
    def setUp(self):
        import configs.load_env as env_mod
        self.env_mod = env_mod
        # reload_env_variables() 按当前 os.environ 重算模块变量；用例结束
        # （patch.dict 已还原环境）后必须再算一次，把模块变量恢复成真实值。
        # 否则 COOKIE_SECURE=True 会留给同进程后续用例——main 的会话中间件
        # 按请求实时读 load_env.COOKIE_SECURE，Secure cookie 在 TestClient
        # 的 http:// 下不会被回传，第二次请求换了新 session，所有依赖
        # "同一会话连续两次请求"的用例都会莫名 400。
        # （顺带：不要用 importlib.reload(env_mod)——它除了重算变量还会重建
        # 整个模块对象，副作用更大，且同样需要这里的 cleanup。）
        self.addCleanup(env_mod.reload_env_variables)

    def test_cookie_secure_flag_controlled_by_env(self):
        with patch.dict(os.environ, {'COOKIE_SECURE': 'True'}):
            self.env_mod.reload_env_variables()
            self.assertTrue(self.env_mod.COOKIE_SECURE)

    def test_cookie_secure_defaults_to_false(self):
        env = {k: v for k, v in os.environ.items() if k != 'COOKIE_SECURE'}
        with patch.dict(os.environ, env, clear=True):
            self.env_mod.reload_env_variables()
            self.assertFalse(self.env_mod.COOKIE_SECURE)

    def test_cookie_max_age_defaults_to_86400(self):
        env = {k: v for k, v in os.environ.items() if k != 'COOKIE_MAX_AGE'}
        with patch.dict(os.environ, env, clear=True):
            self.env_mod.reload_env_variables()
            self.assertEqual(self.env_mod.COOKIE_MAX_AGE, 86400)


if __name__ == '__main__':
    unittest.main()
