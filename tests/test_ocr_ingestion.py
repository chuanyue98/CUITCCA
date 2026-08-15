"""OCR 摄取链路回归测试：图片 -> OCR -> 文本 -> 摄入向量库。

背景（2026-08）：OCR 是可选依赖（``rapidocr-onnxruntime``，`uv sync
--extra ocr` 启用）。仓库里已有的图片解析测试只覆盖两条**非成功**路径——
"依赖未安装 -> 显式报告能力不可用"（``test_document_parsers.py`` /
``test_parsers_registry.py``）和"图片损坏 -> FAILURE"。装上 OCR 之后真正把
流程图文字识别出来、摄入知识库这条**成功路径没有任何测试保护**。缺这条回归
保护的直接后果：任何改动只要破坏了 ``parse_image`` 的结果解包 / ``Source``
处理 / 注册表分派 / 摄取管道对接，CI 里不会有任何测试变红（不管机器装没装
OCR 都测不到成功路径），等真跑线上摄取才发现。

测试不依赖真实 rapidocr（首次调用要下载约 100MB 的识别模型，CI 里不该碰）：
通过 ``sys.modules`` 注入一个假的 ``rapidocr_onnxruntime`` 模块、patch
``_ocr_available`` 为 True，把 OCR 引擎的输出固定成确定性结果，并在假模块上
记录引擎被调用的次数（断言"OCR 真的跑过"而不是文本恰好等于某个硬编码值）。
图片用 PIL 生成一张真实的最小 PNG——Pillow 是 pdfplumber 的强依赖，主依赖集
里一定有，且让 ``Image.open`` 走真实解码路径而不是用假字节糊弄过去。
"""
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from handlers.ingestion_pipeline import build_pipeline, ingest_files
from handlers.parsers.image_parser import parse_image
from handlers.parsers.types import ParseStatus
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.vector_stores.simple import SimpleVectorStore

import tests._pathsetup  # noqa: F401

# 模拟 rapidocr 识别出的几行流程图文字（真实语料里 休学流程.jpg 的内容形态）
_OCR_LINES = ["填写休学（保留学籍）申请表", "家长签署意见", "办理离校手续（退费、退课、退宿舍）"]
# rapidocr 返回的 [box, text, score] 结构，box 随便给个四边形
_BOX = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]


def _success_engine(image):
    """假 OCR 引擎：把 ``_OCR_LINES`` 逐行识别出来，返回 rapidocr 的结果结构。"""
    return [[_BOX, line, 0.93] for line in _OCR_LINES], 0.01


def _make_fake_rapidocr_module(engine_behavior):
    """构造一个可注入 ``sys.modules`` 的假 ``rapidocr_onnxruntime`` 模块。

    ``engine_behavior(image)`` 决定引擎行为：返回 ``(result, elapsed)`` 或抛异常，
    由各测试决定，这样成功/空结果/引擎异常三条分支都能用同一个 fake 框架。
    模块上的 ``calls`` 属性记录引擎被调用的次数，供测试断言"OCR 真的执行了"。
    """

    class _FakeRapidOCR:
        def __call__(self, image):
            mod.calls += 1
            return engine_behavior(image)

    mod = types.ModuleType("rapidocr_onnxruntime")
    mod.calls = 0
    mod.RapidOCR = _FakeRapidOCR
    return mod


@contextmanager
def _ocr_context(engine_behavior):
    """让 ``parse_image`` 走 OCR 成功路径的 mock 上下文，yield 假模块供断言。

    两件事缺一不可：``_ocr_available()`` 要返回 True（否则直接走
    UNAVAILABLE 提前返回），``rapidocr_onnxruntime`` 要在 ``sys.modules`` 里
    能 import 到（``parse_image`` 是在函数体内 ``from rapidocr_onnxruntime
    import RapidOCR`` 的，不注入假的模块就会 ImportError）。
    """
    fake = _make_fake_rapidocr_module(engine_behavior)
    with (
        patch("handlers.parsers.image_parser._ocr_available", return_value=True),
        patch.dict(sys.modules, {"rapidocr_onnxruntime": fake}),
    ):
        yield fake


def _tiny_png_bytes() -> bytes:
    """用 PIL 生成一张真实的最小 PNG。"""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (60, 20), "white").save(buf, format="PNG")
    return buf.getvalue()


class ParseImageOcrSuccessTest(unittest.TestCase):
    """解析器层的成功路径：Path / bytes 两种 Source 输入都要能拿到 OCR 文本。"""

    def test_path_source_returns_joined_ocr_text(self):
        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "休学流程.jpg"
            img_path.write_bytes(_tiny_png_bytes())

            with _ocr_context(_success_engine) as fake:
                result = parse_image(img_path)

        self.assertGreaterEqual(fake.calls, 1, "OCR 引擎必须真的被调用")
        self.assertEqual(result.status, ParseStatus.SUCCESS)
        self.assertEqual(result.text, "\n".join(_OCR_LINES))
        self.assertTrue(result.degraded)
        self.assertIn("OCR", result.reason)

    def test_bytes_source_returns_joined_ocr_text(self):
        """上传/QA 生成链路走 bytes 入参（内存内容，不落盘）。"""
        with _ocr_context(_success_engine) as fake:
            result = parse_image(_tiny_png_bytes())
        self.assertGreaterEqual(fake.calls, 1)
        self.assertEqual(result.status, ParseStatus.SUCCESS)
        self.assertEqual(result.text, "\n".join(_OCR_LINES))

    def test_empty_ocr_result_is_degraded_success_not_failure(self):
        """图片本身没文字（纯图形/流程图截图出错）是"识别成功但没有内容"，
        不是解析失败——上层靠 ``degraded`` 标记感知，不该丢进 parse_failures。"""

        def _empty_engine(image):
            return None, 0.01

        with _ocr_context(_empty_engine):
            result = parse_image(_tiny_png_bytes())

        self.assertEqual(result.status, ParseStatus.SUCCESS)
        self.assertEqual(result.text, "")
        self.assertTrue(result.degraded)
        self.assertIn("未识别", result.reason)

    def test_ocr_engine_exception_is_reported_as_failure(self):
        """引擎崩溃（图片损坏、onnx 模型加载失败等）归类为 FAILURE，带"OCR
        识别失败"前缀——和"依赖没装"的 UNAVAILABLE 区分开（后者见
        test_document_parsers.py 的缺依赖用例）。"""

        def _boom_engine(image):
            raise RuntimeError("onnx 推理炸了")

        with _ocr_context(_boom_engine):
            result = parse_image(_tiny_png_bytes())

        self.assertEqual(result.status, ParseStatus.FAILURE)
        self.assertIn("OCR 识别失败", result.reason)


class OcrIngestRegressionTest(unittest.TestCase):
    """回归保护的核心：图片文件走通完整的 ``ingest_files`` 编排
    （注册表按扩展名分派 -> parse_image -> OCR 文本 -> 切块 -> 嵌入 -> 落
    向量库），OCR 出来的文字和 file_name metadata 必须真实出现在库里。
    """

    def test_image_flows_through_ingest_files_with_ocr_text(self):
        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "休学流程.jpg"
            img_path.write_bytes(_tiny_png_bytes())

            vector_store = SimpleVectorStore()
            pipeline = build_pipeline(
                vector_store=vector_store,
                docstore=SimpleDocumentStore(),
                embed_model=MockEmbedding(embed_dim=8),
            )

            with _ocr_context(_success_engine) as fake:
                result = ingest_files([img_path], pipeline)

        # 摄取编排：图片必须被当作可解析文件收进来，而不是 parse_failure/空文件
        self.assertGreaterEqual(fake.calls, 1)
        self.assertEqual(result.parse_failures, [])
        self.assertEqual(result.empty_files, [])
        self.assertEqual(result.documents_loaded, 1)
        self.assertEqual(result.nodes_upserted, 1)

        # docstore 的公开属性 ``docs``（ref_doc_id -> Document）里就是 pipeline
        # 实际摄取的原始文档：OCR 文本 + 溯源 metadata 都必须原样带进来。
        docstore_docs = pipeline.docstore.docs
        self.assertEqual(len(docstore_docs), 1)
        doc = next(iter(docstore_docs.values()))
        self.assertEqual(doc.text, "\n".join(_OCR_LINES))
        self.assertEqual(doc.metadata.get("file_name"), "休学流程.jpg")
        self.assertIn("last_updated", doc.metadata)

        # 节点（带同样的 metadata）真实落进了向量库。SimpleVectorStore 不存
        # 节点全文（get_nodes 直接 NotImplementedError），但 ``metadata_dict``
        # 是公开属性，检索/引用全靠它：file_name 溯源 + 降级标记都要在。
        # （这两个属性都是对照当前安装的 llama-index 0.14.x 验证过的。）
        node_metadatas = list(vector_store.data.metadata_dict.values())
        self.assertEqual(len(node_metadatas), 1)
        self.assertEqual(node_metadatas[0].get("file_name"), "休学流程.jpg")
        self.assertTrue(node_metadatas[0].get("parse_degraded"))

    def test_ocr_unavailable_image_still_reported_in_parse_failures(self):
        """反向保护：没装 OCR 依赖的机器上图片摄取不能静默跳过——必须出现在
        parse_failures 里（ParserUnavailableError），让调用方知道"本来能处理
        但缺依赖"。这张回归网不能只罩成功路径。"""
        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "流程图.jpg"
            img_path.write_bytes(_tiny_png_bytes())

            vector_store = SimpleVectorStore()
            pipeline = build_pipeline(
                vector_store=vector_store,
                docstore=SimpleDocumentStore(),
                embed_model=MockEmbedding(embed_dim=8),
            )

            with patch("handlers.parsers.image_parser._ocr_available", return_value=False):
                result = ingest_files([img_path], pipeline)

        self.assertEqual(len(result.parse_failures), 1)
        self.assertEqual(result.parse_failures[0][0], img_path)
        self.assertIn("rapidocr", result.parse_failures[0][1].lower())
        self.assertEqual(result.documents_loaded, 0)


if __name__ == "__main__":
    unittest.main()
