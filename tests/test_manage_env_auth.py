import importlib.util
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


def _load_manage_module():
    """Load router/manage.py standalone, bypassing router/__init__.py
    (which eagerly instantiates a HuggingFace embedding model on import)."""
    app_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')
    spec = importlib.util.spec_from_file_location(
        'router_manage_standalone',
        os.path.join(app_dir, 'router', 'manage.py')
    )
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
            response = self.client.get('/manage/env')
        self.assertEqual(response.status_code, 503)

    def test_rejects_wrong_bearer_token(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self.client.get(
                '/manage/env',
                headers={'Authorization': 'Bearer wrongg'},
            )
        self.assertEqual(response.status_code, 401)

    def test_accepts_correct_bearer_token_and_returns_masked_values(self):
        env_file_values = {
            'OPENAI_API_KEY': 'sk-file-key-123456',
            'OPENAI_API_BASE': 'http://file-base',
            'OPENAI_API_MODEL': 'gpt-file',
        }
        with patch.dict(os.environ, {
            'CUITCCA_API_KEY': 'secret123',
            'OPENAI_API_KEY': 'sk-runtime-key-9999',
            'OPENAI_API_BASE': 'http://runtime-base',
            'OPENAI_API_MODEL': 'gpt-runtime',
        }), patch.object(manage, 'dotenv_values', return_value=env_file_values):
            response = self.client.get(
                '/manage/env',
                headers={'Authorization': 'Bearer secret123'},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # API keys must be masked; only the last 4 chars visible
        self.assertEqual(body['env_file']['OPENAI_API_KEY'], '****3456')
        self.assertEqual(body['runtime']['OPENAI_API_KEY'], '****9999')
        # Non-secret config returned as plaintext so operators can confirm
        # which base/model is actually in effect.
        self.assertEqual(body['env_file']['OPENAI_API_BASE'], 'http://file-base')
        self.assertEqual(body['env_file']['OPENAI_API_MODEL'], 'gpt-file')
        self.assertEqual(body['runtime']['OPENAI_API_BASE'], 'http://runtime-base')
        self.assertEqual(body['runtime']['OPENAI_API_MODEL'], 'gpt-runtime')

    def test_masks_short_keys_as_full_asterisks(self):
        # Keys <=4 chars are fully masked to avoid leaking the entire value.
        env_file_values = {'OPENAI_API_KEY': 'ab'}
        with patch.dict(os.environ, {
            'CUITCCA_API_KEY': 'secret123',
            'OPENAI_API_KEY': 'abc',
        }), patch.object(manage, 'dotenv_values', return_value=env_file_values):
            response = self.client.get(
                '/manage/env',
                headers={'Authorization': 'Bearer secret123'},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['env_file']['OPENAI_API_KEY'], '****')
        self.assertEqual(body['runtime']['OPENAI_API_KEY'], '****')

    def test_returns_empty_string_for_missing_keys(self):
        with patch.dict(os.environ, {
            'CUITCCA_API_KEY': 'secret123',
            'OPENAI_API_KEY': '',
            'OPENAI_API_BASE': '',
            'OPENAI_API_MODEL': '',
        }), patch.object(manage, 'dotenv_values', return_value={}):
            response = self.client.get(
                '/manage/env',
                headers={'Authorization': 'Bearer secret123'},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['env_file']['OPENAI_API_KEY'], '')
        self.assertEqual(body['runtime']['OPENAI_API_KEY'], '')


if __name__ == '__main__':
    unittest.main()
