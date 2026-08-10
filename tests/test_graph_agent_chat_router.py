"""backend/app/router/graph.py 里新增的两个 Agent 端点的测试：
``/graph/agent_chat``（非流式）、``/graph/agent_chat_stream``（NDJSON 流式）。

风格上跟 tests/test_graph_router.py 保持一致：mock 掉
``agents.agent_workflow.run_agent``/``stream_agent_events``（graph.py 里是
函数内部延迟 import 的，所以要 patch 定义它们的源模块，不是
``router.graph.run_agent``——跟那边 patch ``handlers.qa_workflow.QAWorkflow``
而不是 ``router.graph.QAWorkflow`` 是同一个原因）。

覆盖：
1. ``/agent_chat`` 成功时返回 ``{"response": ...}``，跟 ``/query`` 同一个
   ``QueryResponse`` 形状；异常时返回统一的 500 兜底文案；调用结束后
   会话历史（``_chat_histories``）和来源（``_last_query_response`` +
   ``/query_sources``）都被正确写入。
2. ``/agent_chat_stream`` 按行输出 NDJSON 事件，content-type 是
   ``application/x-ndjson``；``done`` 事件之后会话历史/来源也被写入；
   过程中出现异常时输出 ``error`` 事件而不是让连接直接断掉。
"""
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from main import app

import tests._pathsetup  # noqa: F401


def _make_source_node(node_id: str, text: str, file_name: str = "a.txt", score: float = 0.9):
    from llama_index.core.schema import NodeWithScore, TextNode

    return NodeWithScore(node=TextNode(id_=node_id, text=text, metadata={"file_name": file_name}), score=score)


def _agent_run_result(response: str, source_nodes=None, tool_calls=None, truncated=False):
    from agents.agent_workflow import AgentRunResult

    return AgentRunResult(
        response=response,
        source_nodes=source_nodes or [],
        tool_calls=tool_calls or [],
        truncated=truncated,
    )


class AgentChatEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("agents.agent_workflow.run_agent")
    def test_agent_chat_success(self, mock_run_agent):
        # 用 side_effect 在调用当下就把 chat_history 快照下来，而不是事后读
        # mock_run_agent.call_args——路由代码在 run_agent() 返回之后还会继续
        # 往同一个 history 列表对象里 append 本轮问答（见 agent_chat 实现），
        # 事后读到的会是追加完的版本，不是调用那一刻传入的值。
        captured: list = []

        async def _capture(query, chat_history=None, **kwargs):
            captured.append(list(chat_history or []))
            return _agent_run_result("agent 给出的答案")

        mock_run_agent.side_effect = _capture

        response = self.client.post("/graph/agent_chat", data={"query": "学校的校训是什么？"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "agent 给出的答案"})
        self.assertEqual(captured, [[]])

    @patch("agents.agent_workflow.run_agent")
    def test_agent_chat_raises_returns_500_fallback(self, mock_run_agent):
        mock_run_agent.side_effect = RuntimeError("boom")

        response = self.client.post("/graph/agent_chat", data={"query": "hello"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(), {"status": "detail", "message": "出错了，请稍后在试一下吧"}
        )

    @patch("agents.agent_workflow.run_agent")
    def test_agent_chat_updates_session_history(self, mock_run_agent):
        mock_run_agent.return_value = _agent_run_result("答案")

        self.client.post("/graph/create")
        response = self.client.post("/graph/agent_chat", data={"query": "问题"})
        self.assertEqual(response.status_code, 200)

        from router.graph import _chat_histories
        client_id = response.cookies.get("session_id") or self.client.cookies.get("session_id")
        history = _chat_histories.get(client_id)
        self.assertIsNotNone(history)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].content, "问题")
        self.assertEqual(history[1].content, "答案")

    @patch("agents.agent_workflow.run_agent")
    def test_agent_chat_populates_query_sources(self, mock_run_agent):
        mock_run_agent.return_value = _agent_run_result(
            "答案", source_nodes=[_make_source_node("n1", "来源原文")]
        )

        self.client.post("/graph/agent_chat", data={"query": "问题"})
        response = self.client.post("/graph/query_sources")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["source_nodes"]), 1)
        self.assertEqual(data["source_nodes"][0]["id"], "n1")
        self.assertEqual(data["source_nodes"][0]["text"], "来源原文")

    @patch("agents.agent_workflow.run_agent")
    def test_agent_chat_forwards_prior_history(self, mock_run_agent):
        captured: list = []

        async def _capture(query, chat_history=None, **kwargs):
            captured.append(list(chat_history or []))
            return _agent_run_result("答案")

        mock_run_agent.side_effect = _capture

        self.client.post("/graph/agent_chat", data={"query": "第一轮问题"})
        response = self.client.post("/graph/agent_chat", data={"query": "第二轮追问"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0], [])  # 第一轮请求时还没有任何历史
        forwarded_history = captured[1]  # 第二轮请求应该带上第一轮的问答
        self.assertEqual(len(forwarded_history), 2)
        self.assertEqual(forwarded_history[0].content, "第一轮问题")


class AgentChatStreamEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @staticmethod
    def _fake_stream_agent_events(events):
        async def _gen(query, chat_history=None, **kwargs):
            for ev in events:
                yield ev

        return _gen

    def test_agent_chat_stream_content_type_is_ndjson(self):
        events = [{"type": "done", "response": "答案", "tool_call_count": 0, "truncated": False}]
        with patch("agents.agent_workflow.stream_agent_events", self._fake_stream_agent_events(events)):
            response = self.client.post("/graph/agent_chat_stream", data={"query": "hi"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers.get("content-type", ""))

    def test_agent_chat_stream_emits_events_in_order_as_ndjson_lines(self):
        events = [
            {"type": "tool_call", "tool_name": "search_knowledge_base", "tool_kwargs": {"query": "校训"}},
            {"type": "tool_result", "tool_name": "search_knowledge_base", "is_error": False, "output": "{}"},
            {"type": "token", "content": "答"},
            {"type": "token", "content": "案"},
            {"type": "done", "response": "答案", "tool_call_count": 1, "truncated": False},
        ]
        with patch("agents.agent_workflow.stream_agent_events", self._fake_stream_agent_events(events)):
            response = self.client.post("/graph/agent_chat_stream", data={"query": "学校的校训是什么？"})

        lines = [line for line in response.text.strip().split("\n") if line]
        parsed = [json.loads(line) for line in lines]
        self.assertEqual([ev["type"] for ev in parsed], [e["type"] for e in events])
        self.assertEqual(parsed[-1]["response"], "答案")

    def test_agent_chat_stream_updates_history_and_sources_after_done(self):
        search_output = json.dumps(
            {"query": "q", "result_count": 1, "results": [
                {"node_id": "n1", "score": 0.9, "file_name": "a.txt", "source_url": None, "text": "原文"}
            ]},
            ensure_ascii=False,
        )
        events = [
            {"type": "tool_result", "tool_name": "search_knowledge_base", "is_error": False,
             "output": search_output},
            {"type": "token", "content": "最终答案"},
            {"type": "done", "response": "最终答案", "tool_call_count": 1, "truncated": False},
        ]
        with patch("agents.agent_workflow.stream_agent_events", self._fake_stream_agent_events(events)):
            response = self.client.post("/graph/agent_chat_stream", data={"query": "问题"})
        self.assertEqual(response.status_code, 200)

        from router.graph import _chat_histories
        client_id = response.cookies.get("session_id") or self.client.cookies.get("session_id")
        history = _chat_histories.get(client_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1].content, "最终答案")

        sources_response = self.client.post("/graph/query_sources")
        self.assertEqual(sources_response.status_code, 200)
        self.assertEqual(len(sources_response.json()["source_nodes"]), 1)

    def test_agent_chat_stream_error_path_yields_error_event(self):
        async def _boom(query, chat_history=None, **kwargs):
            raise RuntimeError("stream boom")
            yield  # pragma: no cover - makes this an async generator function

        with patch("agents.agent_workflow.stream_agent_events", _boom):
            response = self.client.post("/graph/agent_chat_stream", data={"query": "会出错的问题"})

        self.assertEqual(response.status_code, 200)
        lines = [line for line in response.text.strip().split("\n") if line]
        parsed = [json.loads(line) for line in lines]
        self.assertEqual(parsed[-1]["type"], "error")
        self.assertIn("出错了", parsed[-1]["message"])


if __name__ == "__main__":
    unittest.main()
