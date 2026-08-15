"""backend/app/router/graph.py 新增的 /graph/ask_stream 端点的测试。

这是"去掉用户可见的问答模式切换器，改成后端自动路由"的统一入口——不需要
用户先选"标准问答"还是"Agent 模式"，路由判定（``handlers.auto_router.
route_query``）算完自动分发。

风格上跟 ``tests/test_graph_agent_chat_router.py``/``tests/test_graph_router.py``
一致：mock 掉端点内部延迟 import 的三个依赖——``handlers.auto_router.
route_query``/``generate_followup_suggestions``、``agents.agent_workflow.
stream_agent_events``、``handlers.qa_workflow.QAWorkflow``——不碰真实索引、
不联网、不需要配置真实 LLM。

覆盖：
1. standard 分支：``route`` 事件先发出，随后是 QAWorkflow 产出的 token、
   done、suggestions；QAWorkflow 被注入了一个"占位 retriever"（不是 None），
   ``run()`` 带 ``skip_condense=True`` 和路由阶段已经压缩好的
   ``query_str``——验证"不重复检索、不重复压缩"这条硬要求。
2. agent 分支：跟现有 ``/agent_chat_stream`` 同一套事件转发逻辑，
   ``stream_agent_events`` 收到的是**原始** query（不是压缩后的
   ``query_str``），suggestions 在 done 之后追加。
3. 出错路径：route_query 本身抛异常、standard 分支 workflow 抛异常、agent
   分支产出 error 事件，都不应该导致会话历史写入一条空 assistant 消息
   （跟 ``/agent_chat_stream`` 已经修过的坑保持同样的处理方式）。
4. 追问建议生成失败时静默返回空数组，不影响这一轮已经产出的正常回答。
"""
import json
import unittest
from unittest.mock import MagicMock, patch

import configs.load_env as load_env
from fastapi.testclient import TestClient
from main import app

import tests._pathsetup  # noqa: F401


# 语义缓存（handlers/qa_cache.py）在 ask_stream 里是路由判定之前的一步。既有的
# standard/agent/出错路径用例关注的是"路由之后"的行为，一律在 setUp 里把缓存
# 关掉，避免 lookup 真的去查真实 Chroma 库/真实嵌入模型。缓存命中分支的行为
# 由 AskStreamCacheHitTest 单独覆盖。
def _disable_qa_cache(self):
    self._prev_qa_cache_enabled = load_env.QA_CACHE_ENABLED
    load_env.QA_CACHE_ENABLED = False


def _restore_qa_cache(self):
    # setUp 关掉的标志要在 tearDown 恢复，避免全局状态泄漏影响后面跑的测试
    # （当前文件里 AskStreamCacheHitTest 会显式开，但依赖"碰巧排在后面"的
    # 顺序不成立，恢复是正确做法）。
    load_env.QA_CACHE_ENABLED = getattr(self, "_prev_qa_cache_enabled", True)


def _make_source_node(node_id: str, text: str, file_name: str = "a.txt", score: float = 0.9):
    from llama_index.core.schema import NodeWithScore, TextNode

    return NodeWithScore(node=TextNode(id_=node_id, text=text, metadata={"file_name": file_name}), score=score)


def _route_decision(mode: str, nodes=None, query_str: str = "问题", reason: str = "reason"):
    from handlers.auto_router import RouteDecision

    return RouteDecision(mode=mode, nodes=nodes or [], query_str=query_str, reason=reason)


class _FakeQAWorkflowHandler:
    """模拟 ``QAWorkflow(...).run(...)`` 返回的 handler：既能
    ``async for ev in handler.stream_events()``，又能 ``await handler``
    拿到最终结果。跟 ``tests/test_graph_router.py`` 里 ``test_query_stream``
    用的 FakeHandler 是同一个模式。"""

    def __init__(self, tokens, result=None, raise_during_stream: Exception | None = None):
        self._tokens = tokens
        self._result = result
        self._raise_during_stream = raise_during_stream

    async def stream_events(self):
        from handlers.qa_workflow import TokenEvent

        for tok in self._tokens:
            yield TokenEvent(token=tok)
        if self._raise_during_stream is not None:
            raise self._raise_during_stream

    def __await__(self):
        async def _result():
            if self._raise_during_stream is not None:
                raise self._raise_during_stream
            return self._result

        return _result().__await__()


class AskStreamStandardBranchTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        _disable_qa_cache(self)

    def tearDown(self):
        _restore_qa_cache(self)
        app.dependency_overrides.clear()

    @patch("handlers.qa_workflow.QAWorkflow")
    @patch("handlers.auto_router.generate_followup_suggestions")
    @patch("handlers.auto_router.route_query")
    def test_standard_branch_emits_route_token_done_suggestions(
        self, mock_route_query, mock_suggestions, mock_workflow_cls
    ):
        from handlers.qa_workflow import QAWorkflowResult

        nodes = [_make_source_node("n1", "图书馆开馆时间原文")]
        mock_route_query.return_value = _route_decision(
            "standard", nodes=nodes, query_str="压缩后的问题", reason="已检索到高置信度内容"
        )
        mock_suggestions.return_value = ["追问一", "追问二"]

        mock_instance = MagicMock()
        mock_instance.run = MagicMock(
            return_value=_FakeQAWorkflowHandler(
                tokens=["答", "案"],
                result=QAWorkflowResult(response="答案", source_nodes=nodes),
            )
        )
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/ask_stream", data={"query": "图书馆几点开门"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/x-ndjson", response.headers.get("content-type", ""))

        lines = [line for line in response.text.strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        self.assertEqual(
            [e["type"] for e in events], ["route", "token", "token", "done", "suggestions"]
        )
        self.assertEqual(events[0]["mode"], "standard")
        self.assertEqual(events[0]["reason"], "已检索到高置信度内容")
        self.assertEqual(events[1]["content"], "答")
        self.assertEqual(events[2]["content"], "案")
        self.assertEqual(events[3]["response"], "答案")
        self.assertEqual(events[4]["suggestions"], ["追问一", "追问二"])

    @patch("handlers.qa_workflow.QAWorkflow")
    @patch("handlers.auto_router.generate_followup_suggestions")
    @patch("handlers.auto_router.route_query")
    def test_standard_branch_reuses_precomputed_nodes_and_skips_condense(
        self, mock_route_query, mock_suggestions, mock_workflow_cls
    ):
        """核心要求：standard 分支不能重新检索、不能重新压缩问题——QAWorkflow
        应该被注入一个非 None 的 retriever（route_query 已经算好的 nodes），
        并且 run() 带 skip_condense=True、query 用的是路由阶段压缩好的
        query_str，不是原始 query。"""
        from handlers.qa_workflow import QAWorkflowResult

        nodes = [_make_source_node("n1", "原文")]
        mock_route_query.return_value = _route_decision(
            "standard", nodes=nodes, query_str="压缩后的独立问题"
        )
        mock_suggestions.return_value = []

        mock_instance = MagicMock()
        fake_result = QAWorkflowResult(response="答案", source_nodes=nodes)
        mock_instance.run = MagicMock(
            return_value=_FakeQAWorkflowHandler(tokens=["答案"], result=fake_result)
        )
        mock_workflow_cls.return_value = mock_instance

        self.client.post("/graph/ask_stream", data={"query": "原始追问"})

        # QAWorkflow 构造时传入了非 None 的 retriever（占位 retriever，不是
        # None——None 会导致 QAWorkflow 自己用 _build_retriever() 重新检索）。
        _, kwargs = mock_workflow_cls.call_args
        self.assertIsNotNone(kwargs.get("retriever"))

        # run() 用的是路由阶段压缩好的 query_str，且带 skip_condense=True。
        mock_instance.run.assert_called_once()
        _, run_kwargs = mock_instance.run.call_args
        self.assertEqual(run_kwargs.get("query"), "压缩后的独立问题")
        self.assertEqual(run_kwargs.get("skip_condense"), True)
        self.assertEqual(run_kwargs.get("streaming"), True)

    @patch("handlers.qa_workflow.QAWorkflow")
    @patch("handlers.auto_router.generate_followup_suggestions")
    @patch("handlers.auto_router.route_query")
    def test_standard_branch_updates_history_and_sources(
        self, mock_route_query, mock_suggestions, mock_workflow_cls
    ):
        from handlers.qa_workflow import QAWorkflowResult

        nodes = [_make_source_node("n1", "原文内容")]
        mock_route_query.return_value = _route_decision("standard", nodes=nodes, query_str="问题")
        mock_suggestions.return_value = []

        mock_instance = MagicMock()
        fake_result = QAWorkflowResult(response="最终答案", source_nodes=nodes)
        mock_instance.run = MagicMock(
            return_value=_FakeQAWorkflowHandler(tokens=["最终答案"], result=fake_result)
        )
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/ask_stream", data={"query": "问题"})
        self.assertEqual(response.status_code, 200)

        from router.graph import _chat_histories
        client_id = response.cookies.get("session_id") or self.client.cookies.get("session_id")
        history = _chat_histories.get(client_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].content, "问题")
        self.assertEqual(history[1].content, "最终答案")

        sources_response = self.client.post("/graph/query_sources")
        self.assertEqual(sources_response.status_code, 200)
        self.assertEqual(len(sources_response.json()["source_nodes"]), 1)
        self.assertEqual(sources_response.json()["source_nodes"][0]["id"], "n1")

    @patch("handlers.qa_workflow.QAWorkflow")
    @patch("handlers.auto_router.generate_followup_suggestions")
    @patch("handlers.auto_router.route_query")
    def test_standard_branch_workflow_error_yields_error_and_no_history_write(
        self, mock_route_query, mock_suggestions, mock_workflow_cls
    ):
        mock_route_query.return_value = _route_decision("standard")
        mock_suggestions.return_value = []

        mock_instance = MagicMock()
        mock_instance.run = MagicMock(
            return_value=_FakeQAWorkflowHandler(tokens=["部分"], raise_during_stream=RuntimeError("boom"))
        )
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/ask_stream", data={"query": "会出错的问题"})

        self.assertEqual(response.status_code, 200)
        lines = [line for line in response.text.strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("出错了", events[-1]["message"])

        from router.graph import _chat_histories
        client_id = response.cookies.get("session_id") or self.client.cookies.get("session_id")
        history = _chat_histories.get(client_id)
        self.assertIsNone(history)


class AskStreamAgentBranchTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        _disable_qa_cache(self)

    def tearDown(self):
        _restore_qa_cache(self)
        app.dependency_overrides.clear()

    @staticmethod
    def _fake_stream_agent_events(events, captured_calls=None):
        async def _gen(query, chat_history=None, **kwargs):
            if captured_calls is not None:
                captured_calls.append(query)
            for ev in events:
                yield ev

        return _gen

    @patch("handlers.auto_router.generate_followup_suggestions")
    @patch("handlers.auto_router.route_query")
    def test_agent_branch_forwards_events_and_uses_raw_query(self, mock_route_query, mock_suggestions):
        mock_route_query.return_value = _route_decision(
            "agent", query_str="压缩后的问题（不应该被传给 agent）", reason="检索置信度不足"
        )
        mock_suggestions.return_value = []

        agent_events = [
            {"type": "tool_call", "tool_name": "search_knowledge_base", "tool_kwargs": {"query": "校训"}},
            {"type": "tool_result", "tool_name": "search_knowledge_base", "is_error": False, "output": "{}"},
            {"type": "token", "content": "答"},
            {"type": "token", "content": "案"},
            {"type": "done", "response": "答案", "tool_call_count": 1, "truncated": False},
        ]
        captured: list = []

        with patch(
            "agents.agent_workflow.stream_agent_events",
            self._fake_stream_agent_events(agent_events, captured),
        ):
            response = self.client.post("/graph/ask_stream", data={"query": "原始问题"})

        self.assertEqual(response.status_code, 200)
        lines = [line for line in response.text.strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        self.assertEqual(
            [e["type"] for e in events],
            ["route", "tool_call", "tool_result", "token", "token", "done", "suggestions"],
        )
        self.assertEqual(events[0]["mode"], "agent")
        self.assertEqual(events[0]["reason"], "检索置信度不足")

        # agent 分支用的是原始 query，不是路由阶段压缩后的 query_str。
        self.assertEqual(captured, ["原始问题"])

    @patch("handlers.auto_router.generate_followup_suggestions")
    @patch("handlers.auto_router.route_query")
    def test_agent_branch_error_event_does_not_write_empty_history(self, mock_route_query, mock_suggestions):
        """跟 /agent_chat_stream 已经修过的坑保持一致：stream_agent_events
        自己产出 error 事件（不是抛异常）时，不能往会话历史里写一条空的
        assistant 消息。"""
        mock_route_query.return_value = _route_decision("agent")
        mock_suggestions.return_value = []

        agent_events = [{"type": "error", "message": "出错了，请稍后在试一下吧"}]

        with patch("agents.agent_workflow.stream_agent_events", self._fake_stream_agent_events(agent_events)):
            response = self.client.post("/graph/ask_stream", data={"query": "会出错的问题"})

        self.assertEqual(response.status_code, 200)
        from router.graph import _chat_histories
        client_id = response.cookies.get("session_id") or self.client.cookies.get("session_id")
        history = _chat_histories.get(client_id)
        self.assertIsNone(history)

    @patch("handlers.auto_router.generate_followup_suggestions")
    @patch("handlers.auto_router.route_query")
    def test_agent_branch_updates_history_and_sources_after_done(self, mock_route_query, mock_suggestions):
        mock_route_query.return_value = _route_decision("agent")
        mock_suggestions.return_value = []

        search_output = json.dumps(
            {"query": "q", "result_count": 1, "results": [
                {"node_id": "n1", "score": 0.9, "file_name": "a.txt", "source_url": None, "text": "原文"}
            ]},
            ensure_ascii=False,
        )
        agent_events = [
            {"type": "tool_result", "tool_name": "search_knowledge_base", "is_error": False, "output": search_output},
            {"type": "token", "content": "最终答案"},
            {"type": "done", "response": "最终答案", "tool_call_count": 1, "truncated": False},
        ]

        with patch("agents.agent_workflow.stream_agent_events", self._fake_stream_agent_events(agent_events)):
            response = self.client.post("/graph/ask_stream", data={"query": "问题"})
        self.assertEqual(response.status_code, 200)

        from router.graph import _chat_histories
        client_id = response.cookies.get("session_id") or self.client.cookies.get("session_id")
        history = _chat_histories.get(client_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1].content, "最终答案")

        sources_response = self.client.post("/graph/query_sources")
        self.assertEqual(sources_response.status_code, 200)
        self.assertEqual(len(sources_response.json()["source_nodes"]), 1)


class AskStreamCacheHitTest(unittest.TestCase):
    """语义缓存命中分支：/graph/ask_stream 在路由判定之前先查缓存，命中则
    直接复用历史答案——不发 route_query、不检索、不生成，事件流是
    route(cache) -> token -> done -> suggestions([])，会话历史照常更新。"""

    def setUp(self):
        self.client = TestClient(app)
        load_env.QA_CACHE_ENABLED = True

    def tearDown(self):
        app.dependency_overrides.clear()
        load_env.QA_CACHE_ENABLED = False

    @patch("handlers.qa_cache.lookup")
    def test_cache_hit_skips_routing_and_answers_from_cache(self, mock_lookup):
        from handlers.qa_cache import CachedEntry

        mock_lookup.return_value = CachedEntry(
            kind="curated",
            answer="缓存的图书馆答案",
            source_file="图书馆借阅规则.pdf",
            source_text="原文片段",
        )
        with patch("handlers.auto_router.route_query") as mock_route_query:
            response = self.client.post("/graph/ask_stream", data={"query": "图书馆几点开门"})

        self.assertEqual(response.status_code, 200)
        lines = [line for line in response.text.strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        self.assertEqual(
            [e["type"] for e in events], ["route", "token", "done", "suggestions"]
        )
        self.assertEqual(events[0]["mode"], "cache")
        self.assertIn("人工沉淀", events[0]["reason"])
        self.assertEqual(events[1]["content"], "缓存的图书馆答案")
        self.assertEqual(events[2]["response"], "缓存的图书馆答案")
        self.assertEqual(events[3]["suggestions"], [])
        # 缓存命中连路由判定都不跑——这是"命中就是冲着快去的"的核心
        mock_route_query.assert_not_called()

        # 会话历史照常更新（下一轮 condense 能看到这轮问答）
        from router.graph import _chat_histories
        client_id = response.cookies.get("session_id") or self.client.cookies.get("session_id")
        history = _chat_histories.get(client_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].content, "图书馆几点开门")
        self.assertEqual(history[1].content, "缓存的图书馆答案")

        # 命中时 /query_sources 用缓存条目里的来源片段重建占位来源
        sources = self.client.post("/graph/query_sources")
        self.assertEqual(sources.status_code, 200)
        self.assertEqual(len(sources.json()["source_nodes"]), 1)
        self.assertEqual(sources.json()["source_nodes"][0]["file_name"], "图书馆借阅规则.pdf")

    @patch("handlers.auto_router.route_query")
    def test_cache_miss_falls_through_to_normal_flow(self, mock_route_query):
        """lookup 未命中（返回 None）时走正常路由，缓存只是前置一跳。"""
        from handlers.qa_workflow import QAWorkflowResult

        mock_route_query.return_value = _route_decision(
            "standard", nodes=[_make_source_node("n1", "原文")], query_str="问题"
        )
        nodes = [_make_source_node("n1", "原文")]

        with patch("handlers.qa_cache.lookup", return_value=None), \
             patch("handlers.qa_cache.store_auto") as mock_store_auto, \
             patch("handlers.auto_router.generate_followup_suggestions", return_value=[]), \
             patch("handlers.qa_workflow.QAWorkflow") as mock_workflow_cls:
            mock_instance = MagicMock()
            fake_result = QAWorkflowResult(response="答案", source_nodes=nodes)
            mock_instance.run = MagicMock(
                return_value=_FakeQAWorkflowHandler(tokens=["答案"], result=fake_result)
            )
            mock_workflow_cls.return_value = mock_instance

            response = self.client.post("/graph/ask_stream", data={"query": "问题"})

        self.assertEqual(response.status_code, 200)
        lines = [line for line in response.text.strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        self.assertEqual(events[0]["mode"], "standard")
        self.assertEqual(events[-1]["type"], "suggestions")
        # 成功回答后写入自动缓存（best-effort）
        mock_store_auto.assert_called_once()
        self.assertEqual(mock_store_auto.call_args.args[0], "问题")
        self.assertEqual(mock_store_auto.call_args.args[1], "答案")


class AskStreamRouteErrorAndSuggestionFallbackTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        _disable_qa_cache(self)

    def tearDown(self):
        _restore_qa_cache(self)
        app.dependency_overrides.clear()

    @patch("handlers.auto_router.route_query")
    def test_route_query_raises_yields_error_event(self, mock_route_query):
        mock_route_query.side_effect = RuntimeError("route boom")

        response = self.client.post("/graph/ask_stream", data={"query": "hi"})

        self.assertEqual(response.status_code, 200)
        lines = [line for line in response.text.strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("出错了", events[0]["message"])

    @patch("handlers.qa_workflow.QAWorkflow")
    @patch("handlers.auto_router.generate_followup_suggestions")
    @patch("handlers.auto_router.route_query")
    def test_suggestions_generation_failure_is_silent_and_answer_still_delivered(
        self, mock_route_query, mock_suggestions, mock_workflow_cls
    ):
        """追问建议生成失败不能拖垮已经成功产出的主回答：done 事件正常，
        suggestions 事件降级为空列表。"""
        from handlers.qa_workflow import QAWorkflowResult

        nodes = [_make_source_node("n1", "原文")]
        mock_route_query.return_value = _route_decision("standard", nodes=nodes, query_str="问题")
        mock_suggestions.side_effect = RuntimeError("suggestion boom")

        mock_instance = MagicMock()
        fake_result = QAWorkflowResult(response="答案", source_nodes=nodes)
        mock_instance.run = MagicMock(
            return_value=_FakeQAWorkflowHandler(tokens=["答案"], result=fake_result)
        )
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/ask_stream", data={"query": "问题"})

        self.assertEqual(response.status_code, 200)
        lines = [line for line in response.text.strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        self.assertEqual(events[-1]["type"], "suggestions")
        self.assertEqual(events[-1]["suggestions"], [])
        # done 事件（倒数第二个）正常产出，说明主回答没有被建议生成的异常拖垮
        self.assertEqual(events[-2]["type"], "done")
        self.assertEqual(events[-2]["response"], "答案")


if __name__ == "__main__":
    unittest.main()
