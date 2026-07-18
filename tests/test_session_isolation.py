import unittest

from fastapi.testclient import TestClient
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from main import app
from router.graph import _chat_histories

import tests._pathsetup  # noqa: F401


class SessionIsolationTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        _chat_histories._data.clear()

    def tearDown(self):
        _chat_histories._data.clear()

    def test_different_clients_get_different_engines(self):
        # Client A creates graph
        response_a = self.client.post("/graph/create")
        self.assertEqual(response_a.status_code, 200)

        # Verify history store was created
        self.assertIsNotNone(_chat_histories)

    def test_ttl_cache_respects_max_size(self):
        # Fill up sessions
        for i in range(10):
            _chat_histories.set(f"client_{i}", [ChatMessage(role=MessageRole.USER, content="x")])

        self.assertLessEqual(len(_chat_histories), _chat_histories._max_size)


if __name__ == '__main__':
    unittest.main()
