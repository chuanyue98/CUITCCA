"""backend/app/handlers/ingestion_pipeline.py 的测试。

覆盖四块：
1. resolve_authoritative_files 的同名冲突消解规则：纯重复 vs 同目录真冲突
   （按 mtime 取权威版本）vs 跨目录同名冲突（内容不同、无法判断新旧，全部
   保留、用相对路径区分）。以及读取失败的文件被彻底排除、不会静默丢弃或
   顶替可用文件。
2. content_hash / strip_uuid_prefix 的基本行为。
3. IngestionPipeline 的 upsert 行为端到端：内容不变跳过、内容变更重新嵌入。
   用 MockEmbedding + 内存态 SimpleVectorStore，不下载真实模型、不连网。
4. ingest_files() 唯一入口：不同文件名、相同内容的文件在报告里全部被列出，
   不会因为"一个 doc_id 只能映射一个路径"这种简化模型而丢失文件名。
"""
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from handlers.ingestion_pipeline import (
    ConflictResolution,
    build_pipeline,
    content_hash,
    ingest_files,
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

    def _write(self, name: str, content: str, mtime_offset: float = 0.0) -> Path:
        path = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        if mtime_offset:
            now = time.time()
            os.utime(path, (now + mtime_offset, now + mtime_offset))
        return Path(path)

    def test_single_file_per_logical_name_is_kept_as_is(self):
        p = self._write("a.txt", "hello")
        result = resolve_authoritative_files([p])
        self.assertEqual(result.authoritative_files, [p])
        self.assertEqual(result.conflicts, [])
        self.assertEqual(result.unreadable_files, [])

    def test_exact_duplicate_content_same_name_is_not_a_conflict(self):
        """两份文件同名同内容（比如目录镜像出来的重复上传）：不算冲突，只留一份。"""
        p1 = self._write("dup/学校简介.txt", "同一份内容")
        p2 = self._write("dup2/学校简介.txt", "同一份内容", mtime_offset=10)

        result = resolve_authoritative_files([p1, p2])

        self.assertEqual(len(result.authoritative_files), 1)
        self.assertEqual(result.conflicts, [])
        # 内容相同时选 mtime 更新的一份（p2）
        self.assertEqual(result.authoritative_files[0], p2)

    def test_resolve_groups_representatives_by_parent_directory(self):
        """核心行为：不同内容的子簇，代表文件是否同一个父目录决定了"能不能判断
        新旧"。这里构造两组不同 basename 的同名冲突分别验证 same_directory
        True/False 两条分支，用 monkeypatch 把两个不同 basename 的文件"伪装"
        成同一个逻辑分组，绕开"同名同目录在真实文件系统里无法同时存在"的限制。
        """
        # --- 场景 A：同一目录下两个版本（模拟"原地编辑过"）---
        dir_a = os.path.join(self.root, "dir_a")
        os.makedirs(dir_a, exist_ok=True)
        a_old = Path(os.path.join(dir_a, "a_old.txt"))
        a_new = Path(os.path.join(dir_a, "a_new.txt"))
        a_old.write_text("旧内容", encoding="utf-8")
        a_new.write_text("新内容", encoding="utf-8")
        now = time.time()
        os.utime(a_old, (now, now))
        os.utime(a_new, (now + 100, now + 100))

        with patch(
            "handlers.ingestion_pipeline.strip_uuid_prefix",
            side_effect=lambda name: "学校历史.txt",
        ):
            result = resolve_authoritative_files([a_old, a_new])

        self.assertEqual(len(result.conflicts), 1)
        conflict = result.conflicts[0]
        self.assertTrue(conflict.same_directory)
        self.assertEqual(conflict.kept_paths, [a_new])
        self.assertEqual([p for p, _ in conflict.discarded], [a_old])
        self.assertEqual(result.authoritative_files, [a_new])
        # 同目录场景不需要用路径消歧，file_name 走默认的 strip_uuid_prefix
        self.assertNotIn(a_new, result.logical_names)

    def test_resolve_keeps_all_versions_when_conflict_spans_different_directories(self):
        """核心行为：不同目录下的同名不同内容——不装作能判断新旧，全部保留，
        用带目录信息的相对路径区分，不静默丢弃任何一份。"""
        dir_x = os.path.join(self.root, "dir_x", "sub")
        dir_y = os.path.join(self.root, "dir_y")
        os.makedirs(dir_x, exist_ok=True)
        os.makedirs(dir_y, exist_ok=True)
        x_file = Path(os.path.join(dir_x, "x.txt"))
        y_file = Path(os.path.join(dir_y, "y.txt"))
        x_file.write_text("来源 X 的内容", encoding="utf-8")
        y_file.write_text("来源 Y 的内容（完全不相关，纯属同名巧合）", encoding="utf-8")
        now = time.time()
        # mtime 几乎相同（批量拷贝语料的真实情况），刻意不让 mtime 能区分谁"更新"
        os.utime(x_file, (now, now))
        os.utime(y_file, (now + 1, now + 1))

        with patch(
            "handlers.ingestion_pipeline.strip_uuid_prefix",
            side_effect=lambda name: "学校历史.txt",
        ):
            result = resolve_authoritative_files([x_file, y_file], corpus_root=Path(self.root))

        self.assertEqual(len(result.conflicts), 1)
        conflict = result.conflicts[0]
        self.assertFalse(conflict.same_directory)
        self.assertEqual(set(conflict.kept_paths), {x_file, y_file})
        self.assertEqual(conflict.discarded, [], "跨目录冲突不应该丢弃任何一份")

        # 两份文件都必须出现在最终的摄取列表里，一份都不能丢
        self.assertEqual(set(result.authoritative_files), {x_file, y_file})

        # 为了不撞车，两份文件的 file_name 标识要带上目录信息，且互不相同
        self.assertIn(x_file, result.logical_names)
        self.assertIn(y_file, result.logical_names)
        self.assertNotEqual(result.logical_names[x_file], result.logical_names[y_file])
        self.assertIn("dir_x", result.logical_names[x_file])
        self.assertIn("dir_y", result.logical_names[y_file])

        # describe() 用的是"无法判断新旧"这种如实的措辞，不能说"采用更新版本"
        desc = conflict.describe()
        self.assertIn("无法判断新旧", desc)
        self.assertIn("全部保留", desc)
        self.assertNotIn("采用更新版本", desc)

    def test_unreadable_file_is_excluded_and_does_not_win_by_default(self):
        """读取失败的文件必须被彻底排除出 hash 分组/mtime 选择，不能因为它
        mtime 更新就意外顶替一份真正可读的重复文件，也不能静默消失——
        必须出现在 unreadable_files 里。"""
        good_path = self._write("group/文件.txt", "可以正常读取的内容")
        bad_path = Path(os.path.join(self.root, "group", "坏文件.txt"))
        # 用 monkeypatch 让它和 good_path 分到同一个逻辑分组，同时模拟"这个
        # 文件路径存在但读取时抛 OSError"（比如权限问题、软链接损坏等，不用
        # 真的构造一个损坏文件，直接 patch read_bytes）。
        bad_path.write_text("占位", encoding="utf-8")
        now = time.time()
        os.utime(bad_path, (now + 1000, now + 1000))  # mtime 远比 good_path 新

        original_read_bytes = Path.read_bytes

        def _flaky_read_bytes(self):
            if self == bad_path:
                raise OSError("模拟磁盘读取失败")
            return original_read_bytes(self)

        with patch(
            "handlers.ingestion_pipeline.strip_uuid_prefix",
            side_effect=lambda name: "文件.txt",
        ), patch.object(Path, "read_bytes", _flaky_read_bytes):
            result = resolve_authoritative_files([good_path, bad_path])

        self.assertEqual(result.authoritative_files, [good_path], "读取失败的文件不应该被选中")
        self.assertEqual(len(result.unreadable_files), 1)
        self.assertEqual(result.unreadable_files[0][0], bad_path)
        self.assertIn("模拟磁盘读取失败", result.unreadable_files[0][1])
        self.assertEqual(result.conflicts, [], "只剩一个可读文件时不构成冲突")

    def test_all_files_in_group_unreadable_yields_no_authoritative_file(self):
        """一组里所有文件都读取失败：不应该崩溃，也不应该凭空选出一个权威文件。"""
        p1 = self._write("allbad/a.txt", "内容 A")
        p2 = self._write("allbad/b.txt", "内容 B")

        with patch(
            "handlers.ingestion_pipeline.strip_uuid_prefix",
            side_effect=lambda name: "同名.txt",
        ), patch.object(Path, "read_bytes", side_effect=OSError("全部读取失败")):
            result = resolve_authoritative_files([p1, p2])

        self.assertEqual(result.authoritative_files, [])
        self.assertEqual(len(result.unreadable_files), 2)
        self.assertEqual(result.conflicts, [])

    def test_uuid_prefixed_duplicates_are_recognized_as_same_logical_document(self):
        """两次上传同一份文档会各自带不同的 uuid 前缀，但去掉前缀后是同一个逻辑文件名。"""
        p1 = self._write(
            "11111111-1111-1111-1111-111111111111_挂失流程.txt",
            "校园卡挂失请到一卡通服务中心办理。",
        )
        p2 = self._write(
            "22222222-2222-2222-2222-222222222222_挂失流程.txt",
            "校园卡挂失请到一卡通服务中心办理。",
            mtime_offset=5,
        )

        result = resolve_authoritative_files([p1, p2])

        self.assertEqual(
            len(result.authoritative_files), 1, "uuid 前缀不同不应该让 pipeline 把同一份文档当成两份"
        )
        self.assertEqual(result.conflicts, [])


class ConflictResolutionDescribeTest(unittest.TestCase):
    def test_same_directory_describe_mentions_kept_and_discarded(self):
        conflict = ConflictResolution(
            logical_name="学校历史.txt",
            same_directory=True,
            kept_paths=[Path("/a/new.txt")],
            discarded=[(Path("/a/old.txt"), 12345.0)],
            kept_mtime=99999.0,
        )
        desc = conflict.describe()
        self.assertIn("采用更新版本", desc)
        self.assertIn("/a/new.txt", desc)
        self.assertIn("/a/old.txt", desc)

    def test_cross_directory_describe_does_not_claim_a_winner(self):
        conflict = ConflictResolution(
            logical_name="学校历史.txt",
            same_directory=False,
            kept_paths=[Path("/x/a.txt"), Path("/y/b.txt")],
            discarded=[],
        )
        desc = conflict.describe()
        self.assertNotIn("采用更新版本", desc)
        self.assertIn("无法判断新旧", desc)
        self.assertIn("/x/a.txt", desc)
        self.assertIn("/y/b.txt", desc)


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


class IngestFilesTest(unittest.TestCase):
    """ingest_files() 是唯一的批量摄取入口，覆盖它自己的编排逻辑（不是
    IngestionPipeline 本身的 upsert 行为，那部分见上面）。"""

    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = self._tmpdir.name

    def _write(self, rel_path: str, content: str) -> Path:
        path = os.path.join(self.root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return Path(path)

    def _make_pipeline(self):
        return build_pipeline(
            vector_store=SimpleVectorStore(),
            docstore=SimpleDocumentStore(),
            embed_model=MockEmbedding(embed_dim=8),
        )

    def test_different_filenames_with_identical_content_both_appear_in_report(self):
        """两个文件名不同、内容完全相同的文件：pipeline 只会嵌入一次（同一个
        content-hash doc_id），但报告里两个文件名都必须出现，不能因为
        "一个 doc_id 只能映射一个路径"这种简化模型而丢失其中一个。"""
        p1 = self._write("学校简介.txt", "这是学校简介的内容")
        p2 = self._write("学校简介_副本.txt", "这是学校简介的内容")  # 完全相同的内容，不同名字

        pipeline = self._make_pipeline()
        result = ingest_files([p1, p2], pipeline)

        self.assertEqual(result.documents_loaded, 2)
        # 只有一个 doc_id（内容相同），但它映射到两个路径
        self.assertEqual(len(result.doc_id_to_paths), 1)
        (paths,) = result.doc_id_to_paths.values()
        self.assertEqual(set(paths), {p1, p2})
        # pipeline 实际只嵌入了一次
        self.assertEqual(result.nodes_upserted, 1)

    def test_parse_failure_does_not_abort_other_files(self):
        good = self._write("好文件.txt", "正常内容")
        bad = self._write("坏文件.txt", "无所谓内容")

        pipeline = self._make_pipeline()
        with patch(
            "handlers.ingestion_pipeline.documents_from_file",
            side_effect=lambda p, logical_name=None: (_ for _ in ()).throw(ValueError("解析炸了"))
            if p == bad
            else [Document(text="正常内容", doc_id=content_hash("正常内容"), metadata={"file_name": "好文件.txt"})],
        ):
            result = ingest_files([good, bad], pipeline, resolve_conflicts=False)

        self.assertEqual(len(result.parse_failures), 1)
        self.assertEqual(result.parse_failures[0][0], bad)
        self.assertEqual(result.documents_loaded, 1)

    def test_empty_document_is_tracked_and_excluded(self):
        empty_path = self._write("空文件.txt", "   ")  # 只有空白字符
        pipeline = self._make_pipeline()

        result = ingest_files([empty_path], pipeline)

        self.assertEqual(result.empty_files, [empty_path])
        self.assertEqual(result.documents_loaded, 0)
        self.assertEqual(result.nodes_upserted, 0)

    def test_unreadable_files_are_surfaced_in_result(self):
        good = self._write("group/好.txt", "正常内容")
        bad = Path(os.path.join(self.root, "group", "坏.txt"))
        bad.write_text("占位", encoding="utf-8")

        original_read_bytes = Path.read_bytes

        def _flaky_read_bytes(self):
            if self == bad:
                raise OSError("读取失败")
            return original_read_bytes(self)

        pipeline = self._make_pipeline()
        with patch(
            "handlers.ingestion_pipeline.strip_uuid_prefix", side_effect=lambda name: "好.txt"
        ), patch.object(Path, "read_bytes", _flaky_read_bytes):
            result = ingest_files([good, bad], pipeline)

        self.assertEqual(len(result.unreadable_files), 1)
        self.assertEqual(result.unreadable_files[0][0], bad)


if __name__ == '__main__':
    unittest.main()
