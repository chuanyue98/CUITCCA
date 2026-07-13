"""router/graph.py 新增的两个 Phase 3 验证端点（/workflow_query、
/workflow_query_stream）的集成测试。风格参照 tests/test_graph_router.py /
tests/test_main_workflow_http.py：用 TestClient 打真实 HTTP 请求，patch 掉
QAWorkflow 让测试不依赖真实索引/LLM。

不测既有 7 个端点——那些一行没改，覆盖率已经在 test_graph_router.py 里。
"""
import unittest  # noqa: I001 (tests._pathsetup must precede main below)
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import tests._pathsetup  # noqa: F401
from main import app


class WorkflowQueryEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_workflow_query_returns_response_from_workflow_result(self, mock_workflow_cls):
        from handlers.qa_workflow import QAWorkflowResult

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(
            return_value=QAWorkflowResult(response="答案在这里", source_nodes=[])
        )
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/workflow_query", data={"query": "学校的校训是什么？"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "答案在这里"})
        mock_instance.run.assert_awaited_once()
        _, kwargs = mock_instance.run.call_args
        self.assertEqual(kwargs.get("query"), "学校的校训是什么？")
        self.assertEqual(kwargs.get("streaming"), False)

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_workflow_query_returns_500_on_exception(self, mock_workflow_cls):
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(side_effect=RuntimeError("boom"))
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/workflow_query", data={"query": "会出错的问题"})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["status"], "detail")

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_workflow_query_stream_streams_tokens_in_order(self, mock_workflow_cls):
        from handlers.qa_workflow import QAWorkflowResult, TokenEvent

        class FakeHandler:
            async def stream_events(self):
                for tok in ["你", "好", "呀"]:
                    yield TokenEvent(token=tok)

            def __await__(self):
                async def _result():
                    return QAWorkflowResult(response="你好呀", source_nodes=[])
                return _result().__await__()

        mock_instance = MagicMock()
        mock_instance.run = MagicMock(return_value=FakeHandler())
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/workflow_query_stream", data={"query": "打个招呼"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "你好呀")
        mock_instance.run.assert_called_once()
        _, kwargs = mock_instance.run.call_args
        self.assertEqual(kwargs.get("streaming"), True)

    @patch("handlers.qa_workflow.QAWorkflow")
    def test_workflow_query_stream_ignores_non_token_events(self, mock_workflow_cls):
        """stream_events() 按官方文档会把 StopEvent 也吐出来；HTTP 响应体
        只应该包含 TokenEvent 的 token，不能把别的事件类型也塞进去。"""
        from handlers.qa_workflow import QAWorkflowResult, TokenEvent
        from llama_index.core.workflow import StopEvent

        class FakeHandler:
            async def stream_events(self):
                yield TokenEvent(token="A")
                yield StopEvent(result=QAWorkflowResult(response="A", source_nodes=[]))

            def __await__(self):
                async def _result():
                    return QAWorkflowResult(response="A", source_nodes=[])
                return _result().__await__()

        mock_instance = MagicMock()
        mock_instance.run = MagicMock(return_value=FakeHandler())
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/workflow_query_stream", data={"query": "问题"})

        self.assertEqual(response.text, "A")


if __name__ == "__main__":
    unittest.main()
