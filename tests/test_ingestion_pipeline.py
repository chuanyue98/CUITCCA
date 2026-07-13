"""backend/app/handlers/ingestion_pipeline.py 的测试（Phase 2）。

覆盖三块：
1. resolve_authoritative_files 的同名冲突消解规则（纯重复 vs 真冲突，按 mtime
   取权威版本）。
2. content_hash / strip_uuid_prefix 的基本行为。
3. IngestionPipeline 的 upsert 行为端到端：内容不变跳过、内容变更重新嵌入。
   用 MockEmbedding + 内存态 SimpleVectorStore，不下载真实模型、不连网。
"""
import os
import time
import unittest

from handlers.ingestion_pipeline import (
    ConflictResolution,
    build_pipeline,
    content_hash,
    resolve_authoritative_files,
    strip_uuid_prefix,
)
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import Document
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.vector_stores.simple import SimpleVectorStore

import tests._pathsetup  # noqa: F401


class ContentHashAndPrefixTest(unittest.TestCase):
    def test_content_hash_is_deterministic(self):
        self.assertEqual(content_hash("你好世界"), content_hash("你好世界"))

    def test_content_hash_differs_for_different_content(self):
        self.assertNotEqual(content_hash("版本 A"), content_hash("版本 B"))

    def test_strip_uuid_prefix_removes_upload_prefix(self):
        prefixed = "2e436f4b-7a5e-4c2f-ad80-a038f9083783_学校招生就业处概况.txt"
        self.assertEqual(strip_uuid_prefix(prefixed), "学校招生就业处概况.txt")

    def test_strip_uuid_prefix_leaves_plain_name_unchanged(self):
        self.assertEqual(strip_uuid_prefix("学校历史.txt"), "学校历史.txt")


class ResolveAuthoritativeFilesTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = self._tmpdir.name

    def _write(self, name: str, content: str, mtime_offset: float = 0.0) -> str:
        path = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        if mtime_offset:
            now = time.time()
            os.utime(path, (now + mtime_offset, now + mtime_offset))
        return path

    def test_single_file_per_logical_name_is_kept_as_is(self):
        from pathlib import Path

        p = Path(self._write("a.txt", "hello"))
        authoritative, conflicts = resolve_authoritative_files([p])
        self.assertEqual(authoritative, [p])
        self.assertEqual(conflicts, [])

    def test_exact_duplicate_content_same_name_is_not_a_conflict(self):
        """两份文件同名同内容（比如目录镜像出来的重复上传）：不算冲突，只留一份。"""
        from pathlib import Path

        p1 = Path(self._write("dup/学校简介.txt", "同一份内容"))
        p2 = Path(self._write("dup2/学校简介.txt", "同一份内容", mtime_offset=10))

        authoritative, conflicts = resolve_authoritative_files([p1, p2])

        self.assertEqual(len(authoritative), 1)
        self.assertEqual(conflicts, [])
        # 内容相同时选 mtime 更新的一份（p2）
        self.assertEqual(authoritative[0], p2)

    def test_same_name_different_content_picks_newer_mtime_and_reports_conflict(self):
        """真正的同名不同内容冲突：按 mtime 取更新版本，旧版本记录进 conflicts，不静默丢弃。"""
        from pathlib import Path

        old_path = Path(self._write("old/学校历史.txt", "旧版本内容", mtime_offset=0))
        new_path = Path(self._write("new/学校历史.txt", "新版本内容（已勘误）", mtime_offset=100))

        authoritative, conflicts = resolve_authoritative_files([old_path, new_path])

        self.assertEqual(authoritative, [new_path])
        self.assertEqual(len(conflicts), 1)
        conflict = conflicts[0]
        self.assertIsInstance(conflict, ConflictResolution)
        self.assertEqual(conflict.logical_name, "学校历史.txt")
        self.assertEqual(conflict.kept_path, new_path)
        self.assertEqual([p for p, _ in conflict.discarded], [old_path])
        # describe() 不应该抛错，且要点名被舍弃的文件，避免信息被静默丢弃
        desc = conflict.describe()
        self.assertIn("学校历史.txt", desc)
        self.assertIn(str(old_path), desc)

    def test_uuid_prefixed_duplicates_are_recognized_as_same_logical_document(self):
        """两次上传同一份文档会各自带不同的 uuid 前缀，但去掉前缀后是同一个逻辑文件名。"""
        from pathlib import Path

        p1 = Path(
            self._write(
                "11111111-1111-1111-1111-111111111111_挂失流程.txt",
                "校园卡挂失请到一卡通服务中心办理。",
            )
        )
        p2 = Path(
            self._write(
                "22222222-2222-2222-2222-222222222222_挂失流程.txt",
                "校园卡挂失请到一卡通服务中心办理。",
                mtime_offset=5,
            )
        )

        authoritative, conflicts = resolve_authoritative_files([p1, p2])

        self.assertEqual(len(authoritative), 1, "uuid 前缀不同不应该让 pipeline 把同一份文档当成两份")
        self.assertEqual(conflicts, [])


class IngestionPipelineUpsertTest(unittest.TestCase):
    """核心行为验证：内容不变跳过、内容变了才重新嵌入。用 MockEmbedding，不碰真实模型/网络。"""

    def _make_pipeline(self):
        vector_store = SimpleVectorStore()
        docstore = SimpleDocumentStore()
        pipeline = build_pipeline(
            vector_store=vector_store, docstore=docstore, embed_model=MockEmbedding(embed_dim=8)
        )
        return pipeline, vector_store, docstore

    def test_first_run_ingests_all_new_documents(self):
        pipeline, _, _ = self._make_pipeline()
        docs = [
            Document(text="文档A的内容", doc_id=content_hash("文档A的内容")),
            Document(text="文档B的内容", doc_id=content_hash("文档B的内容")),
        ]
        nodes = pipeline.run(documents=docs)
        self.assertEqual(len(nodes), 2)

    def test_rerunning_with_unchanged_content_is_skipped(self):
        pipeline, _, _ = self._make_pipeline()
        text = "不会变化的内容"
        doc = Document(text=text, doc_id=content_hash(text))

        first_nodes = pipeline.run(documents=[doc])
        self.assertEqual(len(first_nodes), 1)

        second_nodes = pipeline.run(documents=[Document(text=text, doc_id=content_hash(text))])
        self.assertEqual(len(second_nodes), 0, "内容没变化应该被 UPSERTS 策略跳过，不重新嵌入")

    def test_changed_content_triggers_reembedding(self):
        pipeline, _, _ = self._make_pipeline()
        doc_id = "stable-logical-id"

        v1_nodes = pipeline.run(documents=[Document(text="第一版内容", doc_id=doc_id)])
        self.assertEqual(len(v1_nodes), 1)

        v2_nodes = pipeline.run(documents=[Document(text="第二版内容，已经改过", doc_id=doc_id)])
        self.assertEqual(len(v2_nodes), 1, "同一 doc_id 内容变了应该重新嵌入")

    def test_mixed_batch_only_reembeds_the_changed_document(self):
        pipeline, _, _ = self._make_pipeline()
        unchanged_text = "始终没变的内容"
        changed_doc_id = "will-change"

        pipeline.run(
            documents=[
                Document(text=unchanged_text, doc_id=content_hash(unchanged_text)),
                Document(text="旧版本", doc_id=changed_doc_id),
            ]
        )

        second_run_nodes = pipeline.run(
            documents=[
                Document(text=unchanged_text, doc_id=content_hash(unchanged_text)),
                Document(text="新版本，内容变了", doc_id=changed_doc_id),
            ]
        )
        self.assertEqual(len(second_run_nodes), 1, "批量摄取里只有真正变化的文档应该被重新处理")


if __name__ == '__main__':
    unittest.main()
