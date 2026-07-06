import importlib.util
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_graph_module(name):
    """Load router/graph.py standalone, bypassing router/__init__.py
    (which eagerly instantiates a HuggingFace embedding model on import)."""
    app_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')
    spec = importlib.util.spec_from_file_location(name, os.path.join(app_dir, 'router', 'graph.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSourceNode:
    def __init__(self, node_id):
        self.node = MagicMock(id_=node_id, text=f'text-{node_id}')
        self.score = 1.0


class FakeQueryResponse:
    def __init__(self, node_id):
        self.response = f'answer-for-{node_id}'
        self.source_nodes = [FakeSourceNode(node_id)]


class QuerySourcesIsolationTest(unittest.TestCase):
    def setUp(self):
        self.graph = _load_graph_module('router_graph_standalone_sources')
        self.app = FastAPI()
        self.app.include_router(self.graph.graph_app, prefix='/graph')
        self.client = TestClient(self.app)

    def _fake_engine_for(self, node_id):
        engine = MagicMock()
        engine.aquery = AsyncMock(return_value=FakeQueryResponse(node_id))
        return engine

    def test_query_sources_does_not_leak_between_clients(self):
        with patch.object(self.graph, 'compose_graph_query_engine', side_effect=lambda: self._fake_engine_for('A')):
            resp = self.client.post('/graph/query', data={'query': 'q1'}, headers={'X-Real-IP': '1.1.1.1'})
        self.assertEqual(resp.status_code, 200)

        with patch.object(self.graph, 'compose_graph_query_engine', side_effect=lambda: self._fake_engine_for('B')):
            resp = self.client.post('/graph/query', data={'query': 'q2'}, headers={'X-Real-IP': '2.2.2.2'})
        self.assertEqual(resp.status_code, 200)

        resp_a = self.client.post('/graph/query_sources', headers={'X-Real-IP': '1.1.1.1'})
        self.assertEqual(resp_a.json()['source_nodes'][0]['id'], 'A')

        resp_b = self.client.post('/graph/query_sources', headers={'X-Real-IP': '2.2.2.2'})
        self.assertEqual(resp_b.json()['source_nodes'][0]['id'], 'B')

    def test_query_sources_is_not_destructive(self):
        with patch.object(self.graph, 'compose_graph_query_engine', side_effect=lambda: self._fake_engine_for('A')):
            self.client.post('/graph/query', data={'query': 'q1'}, headers={'X-Real-IP': '1.1.1.1'})

        first = self.client.post('/graph/query_sources', headers={'X-Real-IP': '1.1.1.1'})
        second = self.client.post('/graph/query_sources', headers={'X-Real-IP': '1.1.1.1'})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200, 'second read of the same query result should not 400')
        self.assertEqual(first.json(), second.json())


class ChatEngineIsolationTest(unittest.TestCase):
    def setUp(self):
        self.graph = _load_graph_module('router_graph_standalone_chat')
        self.app = FastAPI()
        self.app.include_router(self.graph.graph_app, prefix='/graph')
        self.client = TestClient(self.app)

    def _make_fake_engine(self):
        engine = MagicMock()
        fake_stream = MagicMock(response_gen=iter(['chunk']))
        engine.astream_chat = AsyncMock(return_value=fake_stream)
        return engine

    def test_concurrent_clients_get_independent_chat_engines(self):
        engine_a = self._make_fake_engine()
        engine_b = self._make_fake_engine()
        engines = {'1.1.1.1': engine_a, '2.2.2.2': engine_b}

        with patch.object(self.graph, 'compose_graph_chat_egine', side_effect=lambda: engines[self._current_ip]):
            self._current_ip = '1.1.1.1'
            self.client.post('/graph/chat_stream', data={'query': 'hi from A'}, headers={'X-Real-IP': '1.1.1.1'})
            self._current_ip = '2.2.2.2'
            self.client.post('/graph/chat_stream', data={'query': 'hi from B'}, headers={'X-Real-IP': '2.2.2.2'})

        engine_a.reset.assert_called_once()
        engine_b.reset.assert_called_once()
        self.assertNotEqual(engine_a, engine_b)

    def test_query_history_uses_the_calling_clients_engine(self):
        resp = self.client.post('/graph/query_history', headers={'X-Real-IP': '9.9.9.9'})
        self.assertEqual(resp.status_code, 404, 'a client with no prior chat should get 404, not someone elses history')


if __name__ == '__main__':
    unittest.main()
