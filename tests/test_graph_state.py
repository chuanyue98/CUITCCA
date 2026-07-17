import importlib.util
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


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


def _make_workflow_result(node_id):
    from handlers.qa_workflow import QAWorkflowResult
    return QAWorkflowResult(response=f'answer-for-{node_id}', source_nodes=[FakeSourceNode(node_id)])


class QuerySourcesIsolationTest(unittest.TestCase):
    def setUp(self):
        self.graph = _load_graph_module('router_graph_standalone_sources')
        self.app = FastAPI()
        self.app.include_router(self.graph.graph_app, prefix='/graph')
        self.client = TestClient(self.app)

    @staticmethod
    def _fake_workflow_cls(node_id):
        # /graph/query does `workflow = QAWorkflow(timeout=60); await
        # workflow.run(...)` — patch the class so instantiating it returns an
        # instance whose .run() resolves to a result tagged with node_id.
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=_make_workflow_result(node_id))
        mock_cls = MagicMock(return_value=mock_instance)
        return mock_cls

    def test_query_sources_does_not_leak_between_clients(self):
        # Client A uses session_id cookie "session-a"
        with patch('handlers.qa_workflow.QAWorkflow', self._fake_workflow_cls('A')):
            resp = self.client.post('/graph/query', data={'query': 'q1'},
                                    cookies={'session_id': 'session-a'})
        self.assertEqual(resp.status_code, 200)

        # Client B uses session_id cookie "session-b"
        with patch('handlers.qa_workflow.QAWorkflow', self._fake_workflow_cls('B')):
            resp = self.client.post('/graph/query', data={'query': 'q2'},
                                    cookies={'session_id': 'session-b'})
        self.assertEqual(resp.status_code, 200)

        resp_a = self.client.post('/graph/query_sources', cookies={'session_id': 'session-a'})
        self.assertEqual(resp_a.json()['source_nodes'][0]['id'], 'A')

        resp_b = self.client.post('/graph/query_sources', cookies={'session_id': 'session-b'})
        self.assertEqual(resp_b.json()['source_nodes'][0]['id'], 'B')

    def test_query_sources_is_not_destructive(self):
        with patch('handlers.qa_workflow.QAWorkflow', self._fake_workflow_cls('A')):
            self.client.post('/graph/query', data={'query': 'q1'},
                             cookies={'session_id': 'session-a'})

        first = self.client.post('/graph/query_sources', cookies={'session_id': 'session-a'})
        second = self.client.post('/graph/query_sources', cookies={'session_id': 'session-a'})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200, 'second read of the same query result should not 400')
        self.assertEqual(first.json(), second.json())


class ChatHistoryIsolationTest(unittest.TestCase):
    """/graph/chat_stream 现在跑 QAWorkflow(streaming=True) 并从 _chat_histories
    读写多轮历史，取代了原来"每个 client 拿到独立 CondenseQuestionChatEngine
    实例"的隔离机制。这里保留原测试想验证的语义（不同 session 互不干扰、
    同一 session 的历史会累积、不会被静默重置），只是把 mock 目标从
    compose_graph_chat_egine 换成 handlers.qa_workflow.QAWorkflow。"""

    def setUp(self):
        self.graph = _load_graph_module('router_graph_standalone_chat')
        self.app = FastAPI()
        self.app.include_router(self.graph.graph_app, prefix='/graph')
        self.client = TestClient(self.app)

    @staticmethod
    def _make_fake_workflow_cls(token: str, response: str):
        from handlers.qa_workflow import QAWorkflowResult, TokenEvent

        class FakeHandler:
            async def stream_events(self):
                yield TokenEvent(token=token)

            def __await__(self):
                async def _result():
                    return QAWorkflowResult(response=response, source_nodes=[])
                return _result().__await__()

        # The router passes a *reference* to the live, mutable chat_history
        # list (and mutates it after the call, once the turn completes) —
        # MagicMock.call_args would just show that same object's *final*
        # state. Snapshot chat_history synchronously inside run() so the
        # test observes what was actually forwarded at call time.
        history_snapshots: list[list] = []

        def _run(*args, **kwargs):
            history_snapshots.append(list(kwargs.get('chat_history') or []))
            return FakeHandler()

        mock_instance = MagicMock()
        mock_instance.run = MagicMock(side_effect=_run)
        mock_instance.history_snapshots = history_snapshots
        return MagicMock(return_value=mock_instance), mock_instance

    def test_concurrent_clients_get_independent_chat_histories(self):
        cls_a, instance_a = self._make_fake_workflow_cls('chunk', 'answer-a')
        with patch('handlers.qa_workflow.QAWorkflow', cls_a):
            self.client.post('/graph/chat_stream', data={'query': 'hi from A'},
                             cookies={'session_id': 'session-a'})

        cls_b, instance_b = self._make_fake_workflow_cls('chunk', 'answer-b')
        with patch('handlers.qa_workflow.QAWorkflow', cls_b):
            self.client.post('/graph/chat_stream', data={'query': 'hi from B'},
                             cookies={'session_id': 'session-b'})

        # Each session's chat_history should only contain its own turn, not
        # leak the other session's messages.
        history_a = self.graph._chat_histories.get('session-a')
        history_b = self.graph._chat_histories.get('session-b')
        self.assertEqual(history_a[0].content, 'hi from A')
        self.assertEqual(history_b[0].content, 'hi from B')

    def test_repeated_messages_from_the_same_client_accumulate_history(self):
        """chat_history 应该随着同一 session 的多轮对话累积增长，而不是每次
        请求都被静默清空——这是新链路里多轮问答能工作的前提。"""
        cls_1, instance_1 = self._make_fake_workflow_cls('chunk', 'first answer')
        with patch('handlers.qa_workflow.QAWorkflow', cls_1):
            self.client.post('/graph/chat_stream', data={'query': 'first message'},
                             cookies={'session_id': 'session-c'})

        cls_2, instance_2 = self._make_fake_workflow_cls('chunk', 'second answer')
        with patch('handlers.qa_workflow.QAWorkflow', cls_2):
            self.client.post('/graph/chat_stream', data={'query': 'follow-up message'},
                             cookies={'session_id': 'session-c'})

        # Second call's chat_history kwarg should carry the first turn's
        # user/assistant messages, proving history isn't reset in between.
        forwarded_history = instance_2.history_snapshots[0]
        self.assertEqual(len(forwarded_history), 2)
        self.assertEqual(forwarded_history[0].content, 'first message')
        self.assertEqual(forwarded_history[1].content, 'first answer')

        final_history = self.graph._chat_histories.get('session-c')
        self.assertEqual(len(final_history), 4)

    def test_query_history_uses_the_calling_clients_engine(self):
        resp = self.client.post('/graph/query_history', cookies={'session_id': 'session-d'})
        self.assertEqual(resp.status_code, 404, 'a client with no prior chat should get 404, not someone elses history')


if __name__ == '__main__':
    unittest.main()
