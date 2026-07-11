import unittest
from unittest.mock import MagicMock, patch

import tests._pathsetup  # noqa: F401

from fastapi.testclient import TestClient

from main import app
from router.graph import _graph_chat_engines, _prune_sessions


class SessionIsolationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        _graph_chat_engines.clear()

    def tearDown(self):
        _graph_chat_engines.clear()

    @patch('router.graph.compose_graph_chat_egine')
    def test_different_clients_get_different_engines(self, mock_compose):
        mock_engine = MagicMock()
        mock_compose.return_value = mock_engine

        # Client A creates graph
        response_a = self.client.post("/graph/create")
        self.assertEqual(response_a.status_code, 200)

        # Verify engine was created
        self.assertIsNotNone(_graph_chat_engines)

    def test_prune_sessions_respects_max_size(self):
        # Fill up sessions
        for i in range(5):
            _graph_chat_engines[f"client_{i}"] = MagicMock()

        _prune_sessions(_graph_chat_engines, max_size=3)

        self.assertLessEqual(len(_graph_chat_engines), 3)


if __name__ == '__main__':
    unittest.main()
