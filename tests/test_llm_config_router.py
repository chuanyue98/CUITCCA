import os
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)
from tests._router_loader import load_router_module

manage = load_router_module('manage.py')


class LLMConfigAuthTest(unittest.TestCase):
    """三个 llm-config/probe 端点都必须过 CUITCCA_API_KEY 鉴权。"""

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(manage.manage_app, prefix='/manage')
        self.client = TestClient(self.app)

    def test_get_rejects_when_no_api_key_configured(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': ''}):
            response = self.client.get('/manage/llm-config')
        self.assertEqual(response.status_code, 503)

    def test_get_rejects_wrong_bearer_token(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self.client.get('/manage/llm-config', headers={'Authorization': 'Bearer wrongg'})
        self.assertEqual(response.status_code, 401)

    def test_post_config_rejects_when_no_api_key_configured(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': ''}):
            response = self.client.post('/manage/llm-config', json={'api_base': 'http://x', 'model': 'm'})
        self.assertEqual(response.status_code, 503)

    def test_probe_rejects_when_no_api_key_configured(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': ''}):
            response = self.client.post('/manage/llm-probe', json={'api_base': 'http://x'})
        self.assertEqual(response.status_code, 503)


class LLMConfigReadTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(manage.manage_app, prefix='/manage')
        self.client = TestClient(self.app)

    def test_get_returns_masked_key_and_plaintext_base_model(self):
        import configs.load_env as load_env
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
                patch.object(load_env, 'openai_api_key', 'sk-secret-key-9999'), \
                patch.object(load_env, 'openai_api_base', 'http://runtime-base'), \
                patch.object(load_env, 'openai_model', 'test-model'):
            response = self.client.get('/manage/llm-config', headers={'Authorization': 'Bearer secret123'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['api_key_masked'], '****9999')
        self.assertNotIn('sk-secret-key-9999', response.text)
        self.assertEqual(body['api_base'], 'http://runtime-base')
        self.assertEqual(body['model'], 'test-model')


class LLMConfigWriteTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(manage.manage_app, prefix='/manage')
        self.client = TestClient(self.app)
        self._tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False)
        self._tmp.write(
            "# 管理员手工维护的注释，重写后必须逐字保留\n"
            "OPENAI_API_KEY='sk-old-key-1234'\n"
            "OPENAI_API_BASE='http://old-base'\n"
            "OPENAI_MODEL='old-model'\n"
            "CUITCCA_API_KEY='keep-me'\n"
            "EMPTY_KEY=\n"
            "PORT=8522\n"
        )
        self._tmp.close()
        self._env_patcher = patch.object(manage.llm_config, 'ENV_PATH', self._tmp.name)
        self._apply_patcher = patch.object(manage.llm_config, '_apply_runtime')
        self._env_patcher.start()
        self._apply_patcher.start()

    def tearDown(self):
        self._env_patcher.stop()
        self._apply_patcher.stop()
        os.unlink(self._tmp.name)

    def _post(self, payload):
        return self.client.post(
            '/manage/llm-config',
            json=payload,
            headers={'Authorization': 'Bearer secret123'},
        )

    def test_write_updates_target_keys_and_preserves_others(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self._post({'api_base': 'http://new-base', 'model': 'new-model'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['api_base'], 'http://new-base')
        self.assertEqual(body['model'], 'new-model')
        from dotenv import dotenv_values
        values = dotenv_values(self._tmp.name)
        self.assertEqual(values['OPENAI_API_BASE'], 'http://new-base')
        self.assertEqual(values['OPENAI_MODEL'], 'new-model')
        # 未传 api_key：保留旧 key；其他变量原样保留
        self.assertEqual(values['OPENAI_API_KEY'], 'sk-old-key-1234')
        self.assertEqual(values['CUITCCA_API_KEY'], 'keep-me')
        self.assertEqual(values['PORT'], '8522')
        with open(self._tmp.name, encoding='utf-8') as f:
            content = f.read()
        # 行级重写：注释和空值键（KEY=）逐字保留，不能被 dotenv 往返重写丢掉
        self.assertIn('# 管理员手工维护的注释，重写后必须逐字保留', content)
        self.assertIn('EMPTY_KEY=', content)

    def test_write_appends_missing_target_keys(self):
        with open(self._tmp.name, 'w', encoding='utf-8') as f:
            f.write("PORT=8522\n")
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self._post({'api_base': 'http://new-base', 'model': 'new-model', 'api_key': 'sk-new-1'})
        self.assertEqual(response.status_code, 200)
        from dotenv import dotenv_values
        values = dotenv_values(self._tmp.name)
        self.assertEqual(values['OPENAI_API_BASE'], 'http://new-base')
        self.assertEqual(values['OPENAI_MODEL'], 'new-model')
        self.assertEqual(values['OPENAI_API_KEY'], 'sk-new-1')
        self.assertEqual(values['PORT'], '8522')

    def test_write_with_new_key_overrides(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self._post({
                'api_base': 'http://new-base',
                'model': 'new-model',
                'api_key': 'sk-brand-new-8888',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['api_key_masked'], '****8888')
        from dotenv import dotenv_values
        self.assertEqual(dotenv_values(self._tmp.name)['OPENAI_API_KEY'], 'sk-brand-new-8888')

    def test_write_unknown_model_returns_warning(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self._post({'api_base': 'http://new-base', 'model': 'totally-unknown-model'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('上下文窗口', response.json()['warning'])

    def test_write_known_model_has_no_warning(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self._post({'api_base': 'http://new-base', 'model': 'glm-5.2'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['warning'])

    def test_write_rejects_blank_model(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self._post({'api_base': 'http://new-base', 'model': '   '})
        self.assertEqual(response.status_code, 422)

    def test_write_rejects_api_base_without_http_scheme(self):
        # 'not-a-url' 存进 .env 会让所有 LLM 调用静默挂掉，入口就要挡掉
        for bad_base in ('not-a-url', 'ftp://x/v1', '  '):
            with self.subTest(base=bad_base):
                with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
                    response = self._post({'api_base': bad_base, 'model': 'm'})
                self.assertEqual(response.status_code, 422)

    def test_write_rejects_masked_placeholder_key(self):
        # 前端回显 ****xxxx，用户直接点保存不能把占位符覆盖成真 key
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            response = self._post({
                'api_base': 'http://new-base',
                'model': 'new-model',
                'api_key': '****1234',
            })
        self.assertEqual(response.status_code, 422)
        self.assertIn('脱敏', response.json()['detail'])
        from dotenv import dotenv_values
        self.assertEqual(dotenv_values(self._tmp.name)['OPENAI_API_KEY'], 'sk-old-key-1234')

    def test_write_apply_failure_reports_partial_success(self):
        # _apply_runtime 失败时 .env 已落盘：报"热生效失败"而不是"写入失败"
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
                patch.object(manage.llm_config, '_apply_runtime', side_effect=RuntimeError('boom')):
            response = self._post({'api_base': 'http://new-base', 'model': 'new-model'})
        self.assertEqual(response.status_code, 500)
        self.assertIn('热生效失败', response.json()['detail'])
        from dotenv import dotenv_values
        self.assertEqual(dotenv_values(self._tmp.name)['OPENAI_API_BASE'], 'http://new-base')


class LLMProbeTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(manage.manage_app, prefix='/manage')
        self.client = TestClient(self.app)

    def _probe(self, payload):
        return self.client.post(
            '/manage/llm-probe',
            json=payload,
            headers={'Authorization': 'Bearer secret123'},
        )

    def test_probe_success_returns_sorted_models(self):
        fake = httpx.Response(200, json={'data': [{'id': 'model-b'}, {'id': 'model-a'}]})
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
                patch.object(manage.llm_config.httpx, 'get', return_value=fake) as mock_get:
            response = self._probe({'api_base': 'http://gw.io/v1/', 'api_key': 'sk-probe-1'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['models'], ['model-a', 'model-b'])
        self.assertIsNotNone(body['latency_ms'])
        # 尾部斜杠被归一化，key 以 Bearer 头传递，不跟随重定向（SSRF 缓解）
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], 'http://gw.io/v1/models')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer sk-probe-1')
        self.assertFalse(kwargs['follow_redirects'])

    def test_probe_falls_back_to_configured_key(self):
        import configs.load_env as load_env
        fake = httpx.Response(200, json={'data': []})
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
                patch.object(load_env, 'openai_api_key', 'sk-configured-7777'), \
                patch.object(manage.llm_config.httpx, 'get', return_value=fake) as mock_get:
            response = self._probe({'api_base': 'http://gw.io/v1'})
        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer sk-configured-7777')

    def test_probe_http_error_returns_structured_failure(self):
        fake = httpx.Response(401, text='{"error": "bad key"}')
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
                patch.object(manage.llm_config.httpx, 'get', return_value=fake):
            response = self._probe({'api_base': 'http://gw.io/v1'})
        body = response.json()
        self.assertFalse(body['ok'])
        self.assertIn('401', body['error'])

    def test_probe_connection_error_returns_structured_failure(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
                patch.object(
                    manage.llm_config.httpx, 'get',
                    side_effect=httpx.ConnectError('refused'),
                ):
            response = self._probe({'api_base': 'http://unreachable.invalid'})
        body = response.json()
        self.assertFalse(body['ok'])
        self.assertIn('连接失败', body['error'])

    def test_probe_blank_base_rejected_without_network(self):
        # 空/非法 scheme 在 Pydantic 层就是 422，不会发起任何网络请求
        for bad_base in ('   ', 'not-a-url', 'file:///etc/passwd'):
            with self.subTest(base=bad_base):
                with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}), \
                        patch.object(manage.llm_config.httpx, 'get') as mock_get:
                    response = self._probe({'api_base': bad_base})
                self.assertEqual(response.status_code, 422)
                mock_get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
