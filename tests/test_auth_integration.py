"""Integration tests for require_api_key_if_configured across routers.

Fills the gap for require_api_key_if_configured (graph_app, response_app).
Scenarios:
- No CUITCCA_API_KEY: endpoints open (no auth required)
- CUITCCA_API_KEY set: missing/wrong Bearer -> 401; correct -> 200
- WebSocket skips HTTP dependency (auth handled in-endpoint)
"""
import os  # noqa: I001 (tests._pathsetup must precede main below)
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from starlette.status import HTTP_401_UNAUTHORIZED

import tests._pathsetup  # noqa: F401
from main import app


class GraphRouterAuthIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_open_access_when_api_key_not_configured(self, mock_workflow_cls):
        from handlers.qa_workflow import QAWorkflowResult
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=QAWorkflowResult(response="ok", source_nodes=[]))
        mock_workflow_cls.return_value = mock_instance
        with patch.dict(os.environ, {"CUITCCA_API_KEY": ""}):
            response = self.client.post("/graph/query", data={"query": "hi"})
        self.assertEqual(response.status_code, 200)

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_401_when_api_key_configured_but_no_token(self, mock_workflow_cls):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret"}):
            response = self.client.post("/graph/query", data={"query": "hi"})
        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)
        mock_workflow_cls.assert_not_called()

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_401_with_wrong_bearer_token(self, mock_workflow_cls):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret"}):
            response = self.client.post(
                "/graph/query", data={"query": "hi"}, headers={"Authorization": "Bearer wrong"})
        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)
        mock_workflow_cls.assert_not_called()

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_200_with_correct_bearer_token(self, mock_workflow_cls):
        from handlers.qa_workflow import QAWorkflowResult
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=QAWorkflowResult(response="ok", source_nodes=[]))
        mock_workflow_cls.return_value = mock_instance
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret"}):
            response = self.client.post(
                "/graph/query", data={"query": "hi"}, headers={"Authorization": "Bearer secret"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "ok"})

    def test_401_applies_to_create_endpoint_too(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret"}):
            response = self.client.post("/graph/create")
        self.assertEqual(response.status_code, HTTP_401_UNAUTHORIZED)

    def test_create_succeeds_with_correct_token(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "secret"}):
            response = self.client.post("/graph/create", headers={"Authorization": "Bearer secret"})
        self.assertEqual(response.status_code, 200)


class WebsocketAuthBypassTest(unittest.TestCase):
    """require_api_key_if_configured skips websocket connections (type == websocket);
    the WebSocket endpoint does its own token check via query param."""

    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_websocket_rejected_without_api_key(self):
        """When CUITCCA_API_KEY is not set, the WS endpoint itself rejects
        (closing code 1008) -- the router-level dependency would have allowed it."""
        from starlette.websockets import WebSocketDisconnect
        with patch.dict(os.environ, {"CUITCCA_API_KEY": ""}):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self.client.websocket_connect("/graph/query"):
                    pass
        self.assertEqual(ctx.exception.code, 1008)


if __name__ == "__main__":
    unittest.main()
