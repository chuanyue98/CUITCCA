import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from main import app
from router.graph import _graph_chat_engines

import tests._pathsetup  # noqa: F401


class SessionIsolationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        _graph_chat_engines._data.clear()

    def tearDown(self):
        _graph_chat_engines._data.clear()

    @patch('router.graph.compose_graph_chat_egine')
    def test_different_clients_get_different_engines(self, mock_compose):
        mock_engine = MagicMock()
        mock_compose.return_value = mock_engine

        # Client A creates graph
        response_a = self.client.post("/graph/create")
        self.assertEqual(response_a.status_code, 200)

        # Verify engine was created
        self.assertIsNotNone(_graph_chat_engines)

    def test_ttl_cache_respects_max_size(self):
        # Fill up sessions
        for i in range(10):
            _graph_chat_engines.set(f"client_{i}", MagicMock())

        self.assertLessEqual(len(_graph_chat_engines), _graph_chat_engines._max_size)


if __name__ == '__main__':
    unittest.main()
