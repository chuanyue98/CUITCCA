import unittest

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.security import ApiKeyMiddleware


class ApiKeyMiddlewareTest(unittest.TestCase):
    def _build_app(self, api_key):
        app = FastAPI()

        @app.get("/")
        def root():
            return {"ok": True}

        app.add_middleware(ApiKeyMiddleware, api_key=api_key)
        return app

    def test_rejects_missing_token_with_a_clean_401_not_a_500(self):
        """Raising HTTPException inside BaseHTTPMiddleware.dispatch() isn't caught
        by FastAPI's exception handlers and surfaces as a raw 500 instead of the
        intended 401 -- verified empirically against a minimal repro app."""
        client = TestClient(self._build_app("secret123"), raise_server_exceptions=False)
        response = client.get("/")
        self.assertEqual(response.status_code, 401)

    def test_accepts_correct_token(self):
        client = TestClient(self._build_app("secret123"), raise_server_exceptions=False)
        response = client.get("/", headers={"Authorization": "Bearer secret123"})
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
