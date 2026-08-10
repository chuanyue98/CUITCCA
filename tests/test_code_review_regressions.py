"""针对一轮 code review 查出的缺陷的回归测试。

每个用例都对应一个**已经复现过**的真实故障，注释里写清楚"不修会怎样"，
避免以后有人觉得某段防御性代码多余而顺手删掉。
"""
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from dependencies.index_dep import get_index
from fastapi.testclient import TestClient
from handlers.parsers import parse_path
from handlers.parsers.types import DocumentParseError, ParserUnavailableError
from main import app

import tests._pathsetup  # noqa: F401

REPO_ROOT = Path(__file__).resolve().parent.parent
# 这份文档 3 个 piece 里有 1 个是 fCompressed=1（英文正文用单字节存储是 Word
# 的常规行为），是语料里唯一能触发压缩分支的文件。
COMPRESSED_DOC = next(
    REPO_ROOT.joinpath("信息搜集汇总").rglob("附件4—本科生在读证明（普通本科英文版）.doc"), None
)


@unittest.skipUnless(COMPRESSED_DOC is not None, "语料文件缺失")
class LegacyDocCompressedPieceTest(unittest.TestCase):
    """MS-DOC 的 ``FcCompressed``：``fCompressed=1`` 时真实字节偏移是 ``fc/2``。

    修复前这里直接用 ``fc``，压缩分段会从约两倍远的位置开始读，解出来是乱码。
    因为一份文档通常只有部分分段被压缩，表现是"正文读到一半突然变成乱码"——
    这份文件修复前解出来是 ``at Cheng`` 后面接一串 ``ÄÈÊÎÐÔÖÚÜÞà…``，正文被
    截断且混入垃圾字符，还带着 SUCCESS 状态进了知识库。
    """

    def test_compressed_piece_decodes_to_readable_text(self):
        text = parse_path(COMPRESSED_DOC).text
        self.assertIn("Chengdu University of Information Technology", text)

    def test_no_mojibake_run_in_output(self):
        text = parse_path(COMPRESSED_DOC).text
        # cp1252 把高位字节解成的那批拉丁重音字母，正常中英文文档里不该成串出现
        mojibake_chars = "ÄÈÊÎÐÔÖÚÜÞàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ"
        longest = 0
        run = 0
        for ch in text:
            run = run + 1 if ch in mojibake_chars else 0
            longest = max(longest, run)
        self.assertLess(longest, 4, f"输出里出现了长度 {longest} 的疑似乱码串")


class IngestFailureMustNotReportSuccessTest(unittest.TestCase):
    """单文件上传路径必须把解析失败抛出来。

    ``ingest_files`` 为批量场景设计，单个文件失败会被收进
    ``IngestResult.parse_failures`` 然后继续——``_ingest_and_persist`` 如果把
    返回值丢掉，"这个文件根本没进知识库"就完全没人知道，接口照样返回
    ``{"status": "inserted"}``。

    放开 ``ALLOWED_EXTENSIONS`` 之后这不是假想场景：没装 OCR 可选依赖的机器
    上传 .jpg 会走到 ``ParserUnavailableError``，改造前会被白名单 400 拒掉，
    修复前则变成"上传成功、零节点写入"——用静默失败换掉了明确失败。
    """

    def _run_ingest(self, exc):
        from handlers.index_crud import _ingest_and_persist

        fake_result = MagicMock()
        fake_result.documents_loaded = 0
        fake_result.parse_failures = [(Path("x.jpg"), f"{type(exc).__name__}: {exc}")]
        fake_result.unreadable_files = []
        fake_result.empty_files = []

        index = MagicMock()
        index.index_id = "idx"
        with patch("handlers.ingestion_pipeline.ingest_files", return_value=fake_result), \
             patch("handlers.ingestion_pipeline.build_pipeline"), \
             patch("handlers.vector_store.load_or_create_docstore"), \
             patch("handlers.vector_store.persist_docstore") as persist:
            with self.assertRaises(DocumentParseError):
                _ingest_and_persist(index, "x.jpg")
            return persist

    def test_parse_failure_propagates(self):
        self._run_ingest(ParserUnavailableError("OCR 依赖未安装"))

    def test_docstore_is_not_persisted_when_nothing_was_ingested(self):
        """没写入任何东西却把 docstore 落盘，会把"这个 doc 已处理过"的假记忆
        存下来，下次重传相同文件反而被 UPSERTS 当成"没变化"跳过。"""
        persist = self._run_ingest(DocumentParseError("文件损坏"))
        persist.assert_not_called()

    def test_empty_file_is_also_reported(self):
        from handlers.index_crud import _ingest_and_persist

        fake_result = MagicMock()
        fake_result.documents_loaded = 0
        fake_result.parse_failures = []
        fake_result.unreadable_files = []
        fake_result.empty_files = [Path("empty.txt")]

        index = MagicMock()
        index.index_id = "idx"
        with patch("handlers.ingestion_pipeline.ingest_files", return_value=fake_result), \
             patch("handlers.ingestion_pipeline.build_pipeline"), \
             patch("handlers.vector_store.load_or_create_docstore"), \
             patch("handlers.vector_store.persist_docstore"):
            with self.assertRaises(DocumentParseError):
                _ingest_and_persist(index, "empty.txt")


class UploadQaParseFailureTest(unittest.TestCase):
    """``/index/{name}/upload_file_by_QA`` 不能因为解析失败变成 500。

    ``read_file_contents`` 现在解析失败会抛异常（改造前返回空串继续往下走，
    那会拿空内容去让 LLM 生成问答对，凭空捏造一堆 QA 塞进知识库）。路由层
    如果不接住，就是未处理异常 -> 500，而改造前这些格式是干净的 400。
    """

    def setUp(self):
        self.fake_index = MagicMock()
        self.fake_index.index_id = "idx"
        app.dependency_overrides[get_index] = lambda: self.fake_index
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def _post(self):
        return self.client.post(
            "/index/idx/upload_file_by_QA",
            files={"file": ("flow.jpg", BytesIO(b"\xff\xd8\xff not a real jpeg"), "image/jpeg")},
        )

    def test_missing_optional_dependency_returns_503_not_500(self):
        with patch("router.index.read_file_contents", side_effect=ParserUnavailableError("OCR 依赖未安装")):
            resp = self._post()
        self.assertEqual(resp.status_code, 503)
        self.assertIn("OCR", resp.json()["message"])

    def test_parse_failure_returns_400_not_500(self):
        with patch("router.index.read_file_contents", side_effect=DocumentParseError("文件损坏")):
            resp = self._post()
        self.assertEqual(resp.status_code, 400)


class AgentStreamHistoryTest(unittest.TestCase):
    """Agent 流式出错时不能把空的 assistant 消息写进会话历史。

    ``stream_agent_events`` 失败时是 yield 一个 ``error`` 事件后正常返回（不
    抛异常），所以路由里的 ``except`` 接不到。修复前控制流会走到"用拼接的
    token 兜底"，而失败往往发生在一个 token 都没吐之前 -> 写入
    ``content=""`` 的 assistant 消息。后果是下一轮请求把空消息发给 LLM
    （不少 OpenAI 兼容后端直接拒绝），并污染 /graph/chat_stream 的 condense 输入。
    """

    def setUp(self):
        self.client = TestClient(app)

    def test_history_is_not_polluted_when_agent_errors(self):
        from router.graph import _chat_histories

        async def _failing_stream(*args, **kwargs):
            yield {"type": "error", "message": "出错了，请稍后在试一下吧"}

        # 路由里是函数内延迟导入（``from agents.agent_workflow import ...``），
        # 所以要 patch 源模块而不是 router.graph 的属性——和现有
        # tests/test_graph_agent_chat_router.py 的做法保持一致。
        with patch("agents.agent_workflow.stream_agent_events", _failing_stream):
            resp = self.client.post("/graph/agent_chat_stream", data={"query": "测试"})
            self.assertEqual(resp.status_code, 200)
            resp.read()

        for history in _chat_histories._data.values():
            for msg in history[0]:
                self.assertTrue(
                    (msg.content or "").strip(),
                    "会话历史里出现了空的消息，下一轮请求会带着它去调 LLM",
                )


class CrawlStatsThreadSafetyTest(unittest.TestCase):
    """统计计数在线程池里被并发累加，``+=`` 不是原子操作会丢更新。

    这些计数是使用者判断"这次抓取有没有悄悄漏掉页面"的唯一信号，少算一条就
    等于漏掉一次静默失败。
    """

    def test_concurrent_bump_does_not_lose_updates(self):
        from concurrent.futures import ThreadPoolExecutor

        from connectors.web_connector import CrawlStats

        stats = CrawlStats()
        n = 2000
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: stats.bump("failed"), range(n)))
        self.assertEqual(stats.failed, n)


if __name__ == "__main__":
    unittest.main()
