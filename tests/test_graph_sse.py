"""Dedicated tests for the streaming (SSE-like) endpoints in router/graph.py.

Covers aspects not exercised by tests/test_graph_router.py and
tests/test_qa_workflow_router.py:
- Content-Type header is text/plain for all three streaming endpoints
- Token concatenation order across multi-chunk streams
- Source nodes persistence after a stream completes (query_sources works)
"""
import unittest  # noqa: I001 (tests._pathsetup must precede main below)
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import tests._pathsetup  # noqa: F401
from main import app


def _fake_handler(tokens, final_response="full", source_nodes=None):
    from handlers.qa_workflow import QAWorkflowResult, TokenEvent

    class FakeHandler:
        async def stream_events(self):
            for tok in tokens:
                yield TokenEvent(token=tok)

        def __await__(self):
            async def _result():
                return QAWorkflowResult(response=final_response, source_nodes=source_nodes or [])
            return _result().__await__()

    return FakeHandler()


class StreamingContentTypeTest(unittest.TestCase):
    """All streaming endpoints must return Content-Type: text/plain."""

    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_query_stream_content_type(self, mock_workflow_cls):
        mock_instance = MagicMock()
        mock_instance.run = MagicMock(return_value=_fake_handler(["a", "b"], "ab"))
        mock_workflow_cls.return_value = mock_instance
        response = self.client.post("/graph/query_stream", data={"query": "hi"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers.get("content-type", ""))

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_chat_stream_content_type(self, mock_workflow_cls):
        mock_instance = MagicMock()
        mock_instance.run = MagicMock(return_value=_fake_handler(["x", "y"], "xy"))
        mock_workflow_cls.return_value = mock_instance
        response = self.client.post("/graph/chat_stream", data={"query": "hi"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers.get("content-type", ""))

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_workflow_query_stream_content_type(self, mock_workflow_cls):
        mock_instance = MagicMock()
        mock_instance.run = MagicMock(return_value=_fake_handler(["1", "2"], "12"))
        mock_workflow_cls.return_value = mock_instance
        response = self.client.post("/graph/workflow_query_stream", data={"query": "hi"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers.get("content-type", ""))


class StreamingTokenOrderTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_tokens_concatenated_in_order(self, mock_workflow_cls):
        mock_instance = MagicMock()
        mock_instance.run = MagicMock(return_value=_fake_handler(["t1", "t2", "t3"], "t1t2t3"))
        mock_workflow_cls.return_value = mock_instance
        response = self.client.post("/graph/query_stream", data={"query": "q"})
        self.assertEqual(response.text, "t1t2t3")


class StreamingSourcePersistenceTest(unittest.TestCase):
    """After a stream completes, source_nodes should be stored so that
    /query_sources can return them."""

    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_query_stream_persists_sources(self, mock_workflow_cls):
        source_node = MagicMock()
        source_node.node.id_ = "s1"
        source_node.node.text = "source text"
        source_node.score = 0.8
        mock_instance = MagicMock()
        mock_instance.run = MagicMock(return_value=_fake_handler(["ans"], "ans", [source_node]))
        mock_workflow_cls.return_value = mock_instance
        self.client.post("/graph/query_stream", data={"query": "q"})
        response = self.client.post("/graph/query_sources")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["source_nodes"]), 1)
        self.assertEqual(data["source_nodes"][0]["id"], "s1")


if __name__ == "__main__":
    unittest.main()
