import os
import unittest
from unittest.mock import patch

import tests._pathsetup  # noqa: F401

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_503_SERVICE_UNAVAILABLE

from router.manage import manage_app


class RequireConfiguredApiKeyTest(unittest.TestCase):
    def test_returns_503_when_api_key_not_configured(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': ''}):
            app = FastAPI()
            app.include_router(manage_app, prefix='/manage')
            client = TestClient(app)
            response = client.get("/manage/stats")
            self.assertEqual(response.status_code, HTTP_503_SERVICE_UNAVAILABLE)

    def test_returns_401_when_token_missing(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            app = FastAPI()
            app.include_router(manage_app, prefix='/manage')
            client = TestClient(app)
            response = client.get("/manage/stats")
            self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)

    def test_returns_401_when_token_wrong(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            app = FastAPI()
            app.include_router(manage_app, prefix='/manage')
            client = TestClient(app)
            response = client.get(
                "/manage/stats",
                headers={"Authorization": "Bearer wrong"}
            )
            self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)

    def test_accepts_correct_bearer_token(self):
        with patch.dict(os.environ, {'CUITCCA_API_KEY': 'secret123'}):
            app = FastAPI()
            app.include_router(manage_app, prefix='/manage')
            client = TestClient(app)
            response = client.get(
                "/manage/stats",
                headers={"Authorization": "Bearer secret123"}
            )
            self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
