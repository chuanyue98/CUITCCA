"""安全工具函数测试：覆盖 utils/security.py 中的 get_client_ip 和 require_configured_api_key。"""
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_503_SERVICE_UNAVAILABLE,
)

import tests._pathsetup  # noqa: F401
from utils.security import get_client_ip, require_configured_api_key


class GetClientIpTest(unittest.TestCase):
    def _make_request(self, client_host=None):
        request = MagicMock()
        if client_host is None:
            request.client = None
        else:
            request.client = MagicMock()
            request.client.host = client_host
        return request

    def test_returns_client_host_when_available(self):
        request = self._make_request("192.168.1.100")
        self.assertEqual(get_client_ip(request), "192.168.1.100")

    def test_returns_unknown_when_client_is_none(self):
        request = self._make_request(None)
        self.assertEqual(get_client_ip(request), "unknown")

    def test_does_not_trust_x_real_ip_header(self):
        """get_client_ip 不应信任可伪造的 X-Real-IP header"""
        request = self._make_request("10.0.0.1")
        request.headers = {"X-Real-IP": "fake.ip.1.2.3"}
        self.assertEqual(get_client_ip(request), "10.0.0.1")

    def test_does_not_trust_x_forwarded_for_header(self):
        """get_client_ip 不应信任可伪造的 X-Forwarded-For header"""
        request = self._make_request("10.0.0.2")
        request.headers = {"X-Forwarded-For": "fake.ip.4.5.6"}
        self.assertEqual(get_client_ip(request), "10.0.0.2")


class RequireConfiguredApiKeyTest(unittest.TestCase):
    def _make_request(self, auth_header=""):
        request = MagicMock()
        request.headers = {}
        if auth_header:
            request.headers["Authorization"] = auth_header
        return request

    def test_returns_503_when_api_key_not_configured(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": ""}):
            with self.assertRaises(HTTPException) as ctx:
                require_configured_api_key(self._make_request())
        self.assertEqual(ctx.exception.status_code, HTTP_503_SERVICE_UNAVAILABLE)

    def test_returns_401_when_no_authorization_header(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret123"}):
            with self.assertRaises(HTTPException) as ctx:
                require_configured_api_key(self._make_request())
        self.assertEqual(ctx.exception.status_code, HTTP_401_UNAUTHORIZED)

    def test_returns_401_when_wrong_bearer_token(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret123"}):
            with self.assertRaises(HTTPException) as ctx:
                require_configured_api_key(
                    self._make_request("Bearer wrong-token")
                )
        self.assertEqual(ctx.exception.status_code, HTTP_401_UNAUTHORIZED)

    def test_returns_401_when_not_bearer_scheme(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret123"}):
            with self.assertRaises(HTTPException) as ctx:
                require_configured_api_key(
                    self._make_request("Basic secret123")
                )
        self.assertEqual(ctx.exception.status_code, HTTP_401_UNAUTHORIZED)

    def test_passes_with_correct_bearer_token(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret123"}):
            # 不应抛出异常
            require_configured_api_key(
                self._make_request("Bearer secret123")
            )

    def test_uses_constant_time_comparison(self):
        """验证使用 secrets.compare_digest 而非普通 ==，防止时序攻击"""
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret123"}), \
             patch("utils.security.secrets.compare_digest", return_value=False) as mock_cmp:
            with self.assertRaises(HTTPException):
                require_configured_api_key(
                    self._make_request("Bearer secret123")
                )
            mock_cmp.assert_called_once_with("secret123", "secret123")


if __name__ == '__main__':
    unittest.main()
