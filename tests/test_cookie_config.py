import os
import unittest
from unittest.mock import patch

import tests._pathsetup  # noqa: F401


class CookieConfigTest(unittest.TestCase):
    def test_cookie_secure_flag_controlled_by_env(self):
        with patch.dict(os.environ, {'COOKIE_SECURE': 'True'}):
            import importlib

            import configs.load_env as env_mod
            importlib.reload(env_mod)
            self.assertTrue(env_mod.COOKIE_SECURE)

    def test_cookie_secure_defaults_to_false(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove COOKIE_SECURE if set
            env = dict(os.environ)
            env.pop('COOKIE_SECURE', None)
            with patch.dict(os.environ, env, clear=True):
                import importlib

                import configs.load_env as env_mod
                importlib.reload(env_mod)
                self.assertFalse(env_mod.COOKIE_SECURE)

    def test_cookie_max_age_defaults_to_86400(self):
        with patch.dict(os.environ, {}, clear=False):
            env = dict(os.environ)
            env.pop('COOKIE_MAX_AGE', None)
            with patch.dict(os.environ, env, clear=True):
                import importlib

                import configs.load_env as env_mod
                importlib.reload(env_mod)
                self.assertEqual(env_mod.COOKIE_MAX_AGE, 86400)


if __name__ == '__main__':
    unittest.main()
