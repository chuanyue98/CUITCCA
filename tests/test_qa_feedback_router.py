"""backend/app/router/graph.py 新增的 /graph/qa_feedback 与 /graph/cache_stats
端点的测试——反馈闭环的入口：👍 沉淀（写入 curated 缓存 + 反馈表），👎 反馈
（删除缓存条目 + 反馈表）。

风格跟 tests/test_graph_ask_stream_router.py 一致：mock 掉端点内部延迟 import
的缓存操作与反馈落库，不碰真实 Chroma / 真实反馈文件 / 真实嵌入模型。

覆盖：
1. vote=up：store_curated 被调用（带 query/response/来源节点），反馈表写入
   "👍 沉淀"标记的消息。
2. vote=down：delete_by_question 被调用，反馈表写入 "👎 差评"标记。
3. **防投毒校验**：response 不等于本会话最后一条 assistant 消息时返回 400
   （curated 条目会被所有用户以宽松阈值复用，不接受任意问答对）。
4. 非法 vote / 空 query 返回 400。
5. /graph/cache_stats 返回统计字典。
"""
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from main import app

import tests._pathsetup  # noqa: F401


class QaFeedbackEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # 先走 /graph/create 拿到会话 cookie，再往会话历史里种一条
        # USER/ASSISTANT 问答对——防投毒校验要求 response 等于最后一条
        # assistant 消息。
        self.session_id = self.client.post("/graph/create").cookies.get("session_id")
        from router.graph import _chat_histories

        _chat_histories.set(
            self.session_id,
            [
                ChatMessage(role=MessageRole.USER, content="图书馆几点开门"),
                ChatMessage(role=MessageRole.ASSISTANT, content="答案"),
            ],
        )

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("utils.file.save_feedback", new_callable=AsyncMock)
    @patch("handlers.qa_cache.store_curated", new_callable=AsyncMock)
    def test_vote_up_curates_entry_and_records_feedback(self, mock_store, mock_save):
        response = self.client.post(
            "/graph/qa_feedback",
            data={"query": "图书馆几点开门", "response": "答案", "vote": "up"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["vote"], "up")

        # store_curated(query, response, source_nodes)
        self.assertEqual(mock_store.call_args.args[0], "图书馆几点开门")
        self.assertEqual(mock_store.call_args.args[1], "答案")
        mock_save.assert_called_once()
        feedback = mock_save.call_args.args[1]
        self.assertIn("👍 沉淀", feedback.message)

    @patch("utils.file.save_feedback", new_callable=AsyncMock)
    @patch("handlers.qa_cache.delete_by_question", new_callable=AsyncMock)
    def test_vote_down_deletes_cache_and_records_feedback(self, mock_delete, mock_save):
        response = self.client.post(
            "/graph/qa_feedback",
            data={"query": "图书馆几点开门", "response": "答案", "vote": "down"},
        )
        self.assertEqual(response.status_code, 200)
        mock_delete.assert_called_once_with("图书馆几点开门")
        feedback = mock_save.call_args.args[1]
        self.assertIn("👎 差评", feedback.message)

    @patch("utils.file.save_feedback", new_callable=AsyncMock)
    def test_response_not_matching_session_answer_rejected(self, mock_save):
        """防投毒：传编造的问答对（response 不等于会话最后一条 assistant
        消息）时 400，不写缓存也不写反馈表。"""
        response = self.client.post(
            "/graph/qa_feedback",
            data={"query": "图书馆几点开门", "response": "编造的答案", "vote": "up"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not match", response.json()["message"])
        mock_save.assert_not_called()

    def test_no_history_rejected(self):
        """会话历史为空（没有可校验的最后一条回答）时同样拒绝。"""
        from router.graph import _chat_histories

        _chat_histories.set(self.session_id, [])
        response = self.client.post(
            "/graph/qa_feedback",
            data={"query": "q", "response": "a", "vote": "up"},
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_vote_rejected(self):
        response = self.client.post(
            "/graph/qa_feedback",
            data={"query": "q", "response": "a", "vote": "sideways"},
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_query_rejected(self):
        response = self.client.post(
            "/graph/qa_feedback",
            data={"query": "  ", "response": "a", "vote": "up"},
        )
        self.assertEqual(response.status_code, 400)


class CacheStatsEndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("handlers.qa_cache.stats", new_callable=AsyncMock)
    def test_cache_stats_returns_counts(self, mock_stats):
        mock_stats.return_value = {
            "enabled": True,
            "collection": "qa_cache",
            "total": 5,
            "auto": 4,
            "curated": 1,
        }
        response = self.client.post("/graph/cache_stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["auto"], 4)
        self.assertEqual(data["curated"], 1)


if __name__ == "__main__":
    unittest.main()
