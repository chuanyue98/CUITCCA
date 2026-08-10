"""Dedicated tests for the WebSocket /graph/query endpoint.

Complements the basic scenarios in tests/test_graph_router.py
(WebsocketQueryEndpointTest). Focuses on:
- Close code 1008 (Policy Violation) on auth failure
- Multiple round-trips within a single connection
- Query truncation to the 5000-char cap
- Fallback message on workflow exception
"""
import os  # noqa: I001 (tests._pathsetup must precede main below)
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import tests._pathsetup  # noqa: F401
from main import app


def _fallback_message():
    import inspect
    import re

    from router import graph
    src = inspect.getsource(graph)
    m = re.search(r'send_text\(\s*"([^"]+)"\s*\)', src)
    return m.group(1)


class GraphWebsocketCloseCodeTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_close_code_1008_when_api_key_not_configured(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": ""}):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self.client.websocket_connect("/graph/query"):
                    pass
        self.assertEqual(ctx.exception.code, 1008)

    def test_close_code_1008_with_wrong_token(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "correct-key"}):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self.client.websocket_connect("/graph/query?token=wrong"):
                    pass
        self.assertEqual(ctx.exception.code, 1008)

    def test_close_code_1008_without_token_when_key_configured(self):
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "correct-key"}):
            with self.assertRaises(WebSocketDisconnect) as ctx:
                with self.client.websocket_connect("/graph/query"):
                    pass
        self.assertEqual(ctx.exception.code, 1008)


class GraphWebsocketMessagingTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_multiple_round_trips_in_one_session(self, mock_workflow_cls):
        from handlers.qa_workflow import QAWorkflowResult
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(side_effect=[
            QAWorkflowResult(response="answer1", source_nodes=[]),
            QAWorkflowResult(response="answer2", source_nodes=[]),
        ])
        mock_workflow_cls.return_value = mock_instance
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "correct-key"}):
            with self.client.websocket_connect("/graph/query?token=correct-key") as ws:
                ws.send_text("q1")
                self.assertEqual(ws.receive_text(), "answer1")
                ws.send_text("q2")
                self.assertEqual(ws.receive_text(), "answer2")
        self.assertEqual(mock_instance.run.await_count, 2)

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_query_truncated_to_5000_chars(self, mock_workflow_cls):
        from handlers.qa_workflow import QAWorkflowResult
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=QAWorkflowResult(response="ok", source_nodes=[]))
        mock_workflow_cls.return_value = mock_instance
        long_query = "x" * 6000
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "correct-key"}):
            with self.client.websocket_connect("/graph/query?token=correct-key") as ws:
                ws.send_text(long_query)
                ws.receive_text()
        _, kwargs = mock_instance.run.call_args
        self.assertEqual(len(kwargs["query"]), 5000)

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_returns_fallback_on_workflow_exception(self, mock_workflow_cls):
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(side_effect=RuntimeError("boom"))
        mock_workflow_cls.return_value = mock_instance
        with patch.dict(os.environ, {"CUITCCA_API_KEY": "correct-key"}):
            with self.client.websocket_connect("/graph/query?token=correct-key") as ws:
                ws.send_text("hello")
                data = ws.receive_text()
        self.assertEqual(data, _fallback_message())


if __name__ == "__main__":
    unittest.main()
