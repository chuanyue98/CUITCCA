import os
import unittest
from unittest.mock import MagicMock, patch

import tests._pathsetup  # noqa: F401

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_503_SERVICE_UNAVAILABLE

from utils.security import ApiKeyMiddleware, require_configured_api_key
from router.manage import manage_app


class ApiKeyMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.add_middleware(ApiKeyMiddleware, api_key="secret123")
        self.app.include_router(manage_app, prefix='/manage')
        self.client = TestClient(self.app)

    def test_rejects_missing_bearer_token(self):
        response = self.client.get("/manage/stats")
        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)

    def test_rejects_wrong_bearer_token(self):
        response = self.client.get(
            "/manage/stats",
            headers={"Authorization": "Bearer wrong"}
        )
        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)

    def test_accepts_correct_bearer_token(self):
        response = self.client.get(
            "/manage/stats",
            headers={"Authorization": "Bearer secret123"}
        )
        self.assertEqual(response.status_code, 200)


class RequireConfiguredApiKeyTest(unittest.TestCase):
    def test_returns_503_when_api_key_not_configured(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': ''}):
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                require_configured_api_key(None)
            self.assertEqual(ctx.exception.status_code, HTTP_503_SERVICE_UNAVAILABLE)

    def test_returns_401_when_token_missing(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            mock_request = MagicMock()
            mock_request.headers = {}
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                require_configured_api_key(mock_request)
            self.assertEqual(ctx.exception.status_code, HTTP_401_UNAUTHORIZED)


if __name__ == '__main__':
    unittest.main()
