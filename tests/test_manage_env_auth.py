import importlib.util
import os
import unittest
from unittest.mock import patch

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_manage_module():
    """Load router/manage.py standalone, bypassing router/__init__.py
    (which eagerly instantiates a HuggingFace embedding model on import)."""
    app_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')
    spec = importlib.util.spec_from_file_location('router_manage_standalone', os.path.join(app_dir, 'router', 'manage.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manage = _load_manage_module()


class ManageEnvAuthTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(manage.manage_app, prefix='/manage')
        self.client = TestClient(self.app)

    def test_rejects_when_no_api_key_configured(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': ''}):
            response = self.client.post('/manage/env', data={'openai_api_key': 'sk-anything'})
        self.assertEqual(response.status_code, 503)

    def test_rejects_wrong_bearer_token(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self.client.post(
                '/manage/env',
                data={'openai_api_key': 'sk-anything'},
                headers={'Authorization': 'Bearer wrong'},
            )
        self.assertEqual(response.status_code, 401)

    def test_accepts_correct_bearer_token(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
             patch.object(manage, 'dotenv_values', return_value={}), \
             patch.object(manage, 'set_key'), \
             patch.object(manage, 'reload_env_variables'):
            response = self.client.post(
                '/manage/env',
                data={'openai_api_key': 'sk-anything'},
                headers={'Authorization': 'Bearer secret123'},
            )
        self.assertEqual(response.status_code, 200)

    def test_rebuilds_settings_llm_after_updating_env(self):
        """Without this, changing the key/base_url/model via /manage/env has no
        effect on the already-built Settings.llm used by the running query engines."""
        from llama_index.llms.openai_like import OpenAILike
        sentinel_llm = OpenAILike(model='sentinel-model', api_key='x', api_base='http://x',
                                   is_chat_model=True, context_window=10)
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
             patch.object(manage, 'dotenv_values', return_value={}), \
             patch.object(manage, 'set_key'), \
             patch.object(manage, 'reload_env_variables'), \
             patch.object(manage, 'build_llm', return_value=sentinel_llm) as mock_build_llm:
            self.client.post(
                '/manage/env',
                data={'openai_api_key': 'sk-anything'},
                headers={'Authorization': 'Bearer secret123'},
            )
            mock_build_llm.assert_called_once()
            self.assertIs(manage.Settings.llm, sentinel_llm)


if __name__ == '__main__':
    unittest.main()
