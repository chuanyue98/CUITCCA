import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from main import app

import tests._pathsetup  # noqa: F401


class GraphRouterTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    # ── /graph/create ──────────────────────────────────────────────

    @patch('router.graph.compose_graph_chat_egine')
    def test_create(self, mock_compose):
        mock_compose.return_value = MagicMock()

        response = self.client.post("/graph/create")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        mock_compose.assert_called_once()

    # ── /graph/query ───────────────────────────────────────────────

    @patch('router.graph.compose_graph_query_engine')
    def test_query_success(self, mock_compose):
        mock_engine = MagicMock()
        async def mock_aquery(q):
            resp = MagicMock()
            resp.response = "answer text"
            resp.source_nodes = []
            return resp
        mock_engine.aquery = mock_aquery
        mock_compose.return_value = mock_engine

        response = self.client.post("/graph/query", data={"query": "what is this?"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "answer text"})

    @patch('router.graph.compose_graph_query_engine')
    def test_query_empty_response(self, mock_compose):
        mock_engine = MagicMock()
        async def mock_aquery(q):
            resp = MagicMock()
            resp.response = "Empty Response"
            resp.source_nodes = []
            return resp
        mock_engine.aquery = mock_aquery
        mock_compose.return_value = mock_engine

        response = self.client.post("/graph/query", data={"query": "unknown"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "我还不知道，请反馈给我吧"})

    @patch('router.graph.compose_graph_query_engine')
    def test_query_engine_raises(self, mock_compose):
        mock_compose.side_effect = ValueError("broken")

        response = self.client.post("/graph/query", data={"query": "hello"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"status": "detail", "message": "出错了，请稍后在试一下吧"},
        )

    @patch('router.graph.compose_graph_query_engine')
    def test_query_aquery_raises(self, mock_compose):
        mock_engine = MagicMock()
        async def mock_aquery(q):
            raise RuntimeError("query failed")
        mock_engine.aquery = mock_aquery
        mock_compose.return_value = mock_engine

        response = self.client.post("/graph/query", data={"query": "hello"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"status": "detail", "message": "出错了，请稍后在试一下吧"},
        )

    # ── /graph/query_stream ───────────────────────────────────────

    @patch('router.graph.compose_graph_query_engine')
    def test_query_stream(self, mock_compose):
        mock_engine = MagicMock()
        async def mock_aquery(q):
            resp = MagicMock()
            resp.response_gen = iter(["chunk1", "chunk2"])
            resp.get_formatted_sources = MagicMock(return_value="sources")
            resp.source_nodes = []
            return resp
        mock_engine.aquery = mock_aquery
        mock_compose.return_value = mock_engine

        response = self.client.post("/graph/query_stream", data={"query": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "chunk1chunk2")

    # ── /graph/query_sources ──────────────────────────────────────

    @patch('router.graph.compose_graph_query_engine')
    def test_query_sources_returns_sources(self, mock_compose):
        mock_engine = MagicMock()
        source_node = MagicMock()
        source_node.node.id_ = "n1"
        source_node.node.text = "some text"
        source_node.score = 0.95

        async def mock_aquery(q):
            resp = MagicMock()
            resp.response = "answer"
            resp.source_nodes = [source_node]
            return resp
        mock_engine.aquery = mock_aquery
        mock_compose.return_value = mock_engine

        self.client.post("/graph/query", data={"query": "q"})
        response = self.client.post("/graph/query_sources")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["source_nodes"]), 1)
        self.assertEqual(data["source_nodes"][0]["id"], "n1")
        self.assertEqual(data["source_nodes"][0]["text"], "some text")
        self.assertEqual(data["source_nodes"][0]["score"], 0.95)

    def test_query_sources_no_prior_query(self):
        response = self.client.post("/graph/query_sources")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"status": "detail", "message": "please query first"},
        )

    # ── /graph/agent ───────────────────────────────────────────────

    @patch('router.graph.compose_graph_query_engine')
    def test_agent(self, mock_compose):
        mock_engine = MagicMock()
        async def mock_aquery(q):
            resp = MagicMock()
            resp.response = "agent answer"
            resp.source_nodes = []
            return resp
        mock_engine.aquery = mock_aquery
        mock_compose.return_value = mock_engine

        response = self.client.post("/graph/agent", data={"query": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "agent answer"})

    @patch('router.graph.compose_graph_query_engine')
    def test_agent_aquery_raises(self, mock_compose):
        mock_engine = MagicMock()
        async def mock_aquery(q):
            raise RuntimeError("query fail")
        mock_engine.aquery = mock_aquery
        mock_compose.return_value = mock_engine

        response = self.client.post("/graph/agent", data={"query": "hello"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {"status": "detail", "message": "出错了，请稍后在试一下吧"},
        )

    # ── /graph/query_history ──────────────────────────────────────

    @patch('router.graph.compose_graph_chat_egine')
    def test_query_history_success(self, mock_compose):
        fake_chat_engine = MagicMock()
        fake_chat_engine.chat_history = []
        mock_compose.return_value = fake_chat_engine

        self.client.post("/graph/create")
        response = self.client.post("/graph/query_history")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"history": []})

    def test_query_history_not_found(self):
        response = self.client.post("/graph/query_history")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"status": "detail", "message": "No query graph available"},
        )

    # ── /graph/query_router ───────────────────────────────────────

    @patch('handlers.graph_builder.MultiIndexQueryEngine')
    def test_query_router(self, mock_multi_engine_cls):
        import router.graph as rg
        rg.indexes = [MagicMock()]

        mock_engine = MagicMock()
        async def mock_aquery(q):
            resp = MagicMock()
            resp.__str__ = lambda self: "router response"
            return resp
        mock_engine.aquery = mock_aquery
        mock_multi_engine_cls.return_value = mock_engine

        response = self.client.post("/graph/query_router", data={"query": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "router response"})
        mock_multi_engine_cls.assert_called_once()
        del rg.indexes

    # ── /graph/chat_stream ────────────────────────────────────────

    @patch('router.graph.compose_graph_chat_egine')
    def test_chat_stream_creates_engine_if_missing(self, mock_compose):
        fake_engine = MagicMock()
        async def mock_astream_chat(q):
            resp = MagicMock()
            resp.response_gen = iter(["chat", "response"])
            return resp
        fake_engine.astream_chat = mock_astream_chat
        mock_compose.return_value = fake_engine

        response = self.client.post("/graph/chat_stream", data={"query": "hi"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "chatresponse")

    @patch('router.graph.compose_graph_chat_egine')
    def test_chat_stream_uses_existing_engine(self, mock_compose):
        fake_engine = MagicMock()
        async def mock_astream_chat(q):
            resp = MagicMock()
            resp.response_gen = iter(["existing"])
            return resp
        fake_engine.astream_chat = mock_astream_chat
        mock_compose.return_value = fake_engine

        self.client.post("/graph/create")
        response = self.client.post("/graph/chat_stream", data={"query": "hi"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "existing")


if __name__ == '__main__':
    unittest.main()
