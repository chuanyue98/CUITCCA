"""``handlers/chunking.py`` 的表格感知分块。

背景：解析器把 PDF/docx/pptx 里的表格还原成 Markdown 表格保住行列结构，但
``SentenceSplitter`` 只认句子边界和字符数，会把表格从中间切断——续接部分丢掉
表头，变成一堆没有列名的裸数据行。实测全语料 20/294（6.8%）的 chunk 有这个
问题。这组测试钉住"表格是原子单位"这个契约。
"""
import unittest

from handlers.chunking import TableAwareSentenceSplitter, _segment_text, _split_table_preserving_header
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document

import tests._pathsetup  # noqa: F401

TABLE = "\n".join(
    ["| 读者类型 | 允许借书总册数 | 正常借期 | 允许续借次数 |", "| --- | --- | --- | --- |"]
    + [f"| 读者{i} | {i}册 | {i}个月 | 1次 |" for i in range(1, 40)]
)


def _has_orphan_table_rows(text: str) -> bool:
    """有表格数据行、却没有表头分隔线 —— 就是"表头被留在上一个 chunk"的形态。"""
    return text.count("|") > 4 and "| --- |" not in text


class SegmentTextTest(unittest.TestCase):
    def test_splits_prose_and_table_apart(self):
        text = "前面一段说明。\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n后面一段说明。"
        segments = _segment_text(text)
        kinds = [is_table for is_table, _ in segments]
        self.assertEqual(kinds, [False, True, False])
        self.assertIn("前面一段说明", segments[0][1])
        self.assertIn("| --- |", segments[1][1])
        self.assertIn("后面一段说明", segments[2][1])

    def test_header_row_above_separator_is_included_in_table(self):
        segments = _segment_text("| A | B |\n| --- | --- |\n| 1 | 2 |")
        self.assertEqual(len(segments), 1)
        self.assertTrue(segments[0][0])
        self.assertIn("| A | B |", segments[0][1])

    def test_plain_text_without_tables_stays_one_segment(self):
        segments = _segment_text("完全没有表格的一段话。\n第二行。")
        self.assertEqual([is_table for is_table, _ in segments], [False])

    def test_stray_pipe_in_prose_is_not_mistaken_for_a_table(self):
        """判定依据是分隔线行，不是"有竖线"——正文里偶尔出现的竖线不该被误判。"""
        segments = _segment_text("命令写作 a|b 的形式，注意转义。")
        self.assertEqual([is_table for is_table, _ in segments], [False])

    def test_alignment_colons_in_separator_are_recognised(self):
        segments = _segment_text("| A | B |\n|:---|---:|\n| 1 | 2 |")
        self.assertTrue(segments[0][0])


def _chars(text: str) -> int:
    """测试里用字符数当"大小"，只是为了让断言直观、和分词器实现解耦。

    生产代码传的是 ``SentenceSplitter._token_size``（token 计量）——``chunk_size``
    本来就是 token 预算，早期实现拿 ``len()`` 数字符去比是个真实缺陷：中文一个
    字往往不止 1 个 token，含表格的文档会成块地超出配置上限。
    """
    return len(text)


class SplitTablePreservingHeaderTest(unittest.TestCase):
    def test_every_part_repeats_the_header(self):
        parts = _split_table_preserving_header(TABLE, 200, _chars)
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertIn("| 读者类型 | 允许借书总册数 | 正常借期 | 允许续借次数 |", part)
            self.assertIn("| --- |", part)

    def test_no_data_row_is_lost(self):
        parts = _split_table_preserving_header(TABLE, 200, _chars)
        joined = "\n".join(parts)
        for i in range(1, 40):
            self.assertIn(f"| 读者{i} |", joined)

    def test_headerless_table_degrades_to_plain_row_split(self):
        """解析出来的表格第一行就是数据时，重复一个不存在的表头没有意义。"""
        rows = "\n".join(f"| 值{i} | {i} |" for i in range(30))
        parts = _split_table_preserving_header(rows, 100, _chars)
        self.assertGreater(len(parts), 1)
        self.assertNotIn("| --- |", "".join(parts))


class ChunkBudgetUnitTest(unittest.TestCase):
    """``chunk_size`` 是 token 预算，不是字符数——含表格的文档不能系统性超限。"""

    def test_chunks_respect_the_token_budget(self):
        splitter = TableAwareSentenceSplitter.from_defaults(chunk_size=256)
        text = "前言。\n\n" + TABLE + "\n\n" + "这是一段用于填充的中文正文内容。" * 40
        for chunk in splitter.split_text(text):
            self.assertLessEqual(
                splitter._token_size(chunk), splitter.chunk_size,
                "chunk 超出了配置的 token 预算——说明预算又被按字符数比了",
            )


class TableAwareSplitterTest(unittest.TestCase):
    def test_small_table_is_never_split(self):
        text = "说明段落。\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n结尾段落。"
        chunks = TableAwareSentenceSplitter.from_defaults().split_text(text)
        table_chunks = [c for c in chunks if "| --- |" in c]
        self.assertEqual(len(table_chunks), 1)
        self.assertIn("| 1 | 2 |", table_chunks[0])

    def test_large_table_never_produces_orphan_rows(self):
        """核心契约：无论怎么切，都不能出现"有数据行但没表头"的 chunk。"""
        text = "前言。\n\n" + TABLE + "\n\n结语。"
        splitter = TableAwareSentenceSplitter.from_defaults(chunk_size=300)
        chunks = splitter.split_text(text)
        orphans = [c for c in chunks if _has_orphan_table_rows(c)]
        self.assertEqual(orphans, [], f"出现了丢表头的 chunk: {orphans[:1]}")

    def test_improves_on_plain_sentence_splitter(self):
        """同一份输入，父类会切出孤儿行，子类不会——这就是这个类存在的理由。"""
        text = "前言。\n\n" + TABLE + "\n\n结语。"
        plain = SentenceSplitter.from_defaults(chunk_size=300).split_text(text)
        aware = TableAwareSentenceSplitter.from_defaults(chunk_size=300).split_text(text)

        self.assertGreater(sum(1 for c in plain if _has_orphan_table_rows(c)), 0)
        self.assertEqual(sum(1 for c in aware if _has_orphan_table_rows(c)), 0)

    def test_behaviour_unchanged_for_text_without_tables(self):
        """没有表格时必须与父类逐字节一致——这是"安全的原地替换"的前提。"""
        text = "。".join(f"这是第{i}句话，用于测试分块行为是否与父类保持一致" for i in range(60)) + "。"
        plain = SentenceSplitter.from_defaults(chunk_size=200).split_text(text)
        aware = TableAwareSentenceSplitter.from_defaults(chunk_size=200).split_text(text)
        self.assertEqual(plain, aware)

    def test_no_content_is_lost(self):
        text = "前言段落。\n\n" + TABLE + "\n\n结语段落。"
        chunks = TableAwareSentenceSplitter.from_defaults(chunk_size=300).split_text(text)
        joined = "".join(chunks)
        self.assertIn("前言段落", joined)
        self.assertIn("结语段落", joined)
        for i in range(1, 40):
            self.assertIn(f"| 读者{i} |", joined)

    def test_works_through_node_parser_interface(self):
        """生产链路走的是 NodeParser 的 get_nodes_from_documents（内部调
        split_text_metadata_aware），不是直接调 split_text——这条路径必须也走到
        我们的实现，否则改了等于没改。"""
        doc = Document(text="前言。\n\n" + TABLE, metadata={"file_name": "借阅规则.txt"})
        nodes = TableAwareSentenceSplitter.from_defaults(chunk_size=300).get_nodes_from_documents([doc])
        orphans = [n.get_content() for n in nodes if _has_orphan_table_rows(n.get_content())]
        self.assertEqual(orphans, [])


if __name__ == "__main__":
    unittest.main()
