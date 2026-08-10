"""front-matter -> Document metadata 的提升逻辑。

背景：Web 连接器抓回来的语料是"YAML front-matter + Markdown 正文"。如果摄取
时不拆这个头，会同时踩两个坑——那段 YAML 被当成正文送去 embedding（纯噪音），
而 ``source_url``/``publish_date``/``category`` 这些本该用于检索过滤和引用
溯源的字段一个都进不了 metadata。这组测试把这两件事都钉住。
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from handlers.ingestion_pipeline import documents_from_file
from handlers.parsers.front_matter import promoted_metadata, split_front_matter

import tests._pathsetup  # noqa: F401

CRAWLED_MD = """---
source_url: https://www.cuit.edu.cn/info/1006/16903.htm
title: 关于2026年度本科专业拟设置情况的公示
publish_date: '2026-08-05'
category: 通知公告
site: main
crawled_at: '2026-08-08T06:32:46+00:00'
content_hash: abc123
---

# 关于2026年度本科专业拟设置情况的公示

根据教育部有关文件要求，现将我校2026年度拟设置本科专业情况予以公示。
"""


class SplitFrontMatterTest(unittest.TestCase):
    def test_splits_metadata_and_body(self):
        fm, body = split_front_matter(CRAWLED_MD)
        self.assertEqual(fm["category"], "通知公告")
        self.assertEqual(fm["publish_date"], "2026-08-05")
        self.assertTrue(body.startswith("# 关于2026"))
        self.assertNotIn("source_url:", body)

    def test_plain_markdown_is_returned_untouched(self):
        text = "# 普通标题\n\n没有 front-matter 的正文。"
        fm, body = split_front_matter(text)
        self.assertEqual(fm, {})
        self.assertEqual(body, text)

    def test_horizontal_rule_in_body_does_not_truncate(self):
        """Markdown 的水平线也写作 ---，不能用裸 find('---') 找结束分隔符，
        否则正文里出现分隔线会把 front-matter 提前截断、正文被腰斩。"""
        text = "---\ntitle: T\n---\n\n正文第一段\n\n---\n\n正文第二段\n"
        fm, body = split_front_matter(text)
        self.assertEqual(fm["title"], "T")
        self.assertIn("正文第一段", body)
        self.assertIn("正文第二段", body)

    def test_broken_yaml_never_loses_the_body(self):
        """头部格式坏掉不该让整篇内容进不了知识库——退化成"当作没有 metadata
        的普通 Markdown"是安全的降级。"""
        text = "---\n: : : 不是合法 YAML : :\n---\n\n这段正文必须保住。"
        fm, body = split_front_matter(text)
        self.assertEqual(fm, {})
        self.assertIn("这段正文必须保住", body)

    def test_non_mapping_front_matter_is_ignored(self):
        text = "---\n- 这是个列表不是字典\n---\n\n正文"
        fm, body = split_front_matter(text)
        self.assertEqual(fm, {})
        self.assertIn("正文", body)


class PromotedMetadataTest(unittest.TestCase):
    def test_only_whitelisted_keys_are_promoted(self):
        """白名单而不是"有什么塞什么"：metadata 参与 TextNode.hash 计算，
        也会跟着 chunk 进 embedding 和 LLM 上下文，塞无关字段既容易让增量
        去重失效，又浪费 token。"""
        fm, _ = split_front_matter(CRAWLED_MD)
        promoted = promoted_metadata(fm)
        self.assertIn("source_url", promoted)
        self.assertIn("category", promoted)
        self.assertNotIn("content_hash", promoted)
        self.assertNotIn("crawled_at", promoted)

    def test_none_valued_fields_are_omitted_not_stringified(self):
        """静态页面解析不到发布日期时 publish_date 是 None，写成字符串
        "None" 会让下游以为"有这么个日期"。缺字段和字段为空是两回事。"""
        promoted = promoted_metadata({"title": "T", "publish_date": None})
        self.assertNotIn("publish_date", promoted)
        self.assertEqual(promoted["title"], "T")

    def test_blank_strings_are_omitted(self):
        self.assertNotIn("category", promoted_metadata({"category": "   "}))


class DocumentsFromFileMetadataTest(unittest.TestCase):
    def _write(self, tmp: str, name: str, text: str) -> Path:
        path = Path(tmp) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_crawled_markdown_gets_provenance_metadata(self):
        with TemporaryDirectory() as tmp:
            path = self._write(tmp, "crawled.md", CRAWLED_MD)
            docs = documents_from_file(path)

        self.assertEqual(len(docs), 1)
        meta = docs[0].metadata
        self.assertEqual(meta["source_url"], "https://www.cuit.edu.cn/info/1006/16903.htm")
        self.assertEqual(meta["category"], "通知公告")
        self.assertEqual(meta["site"], "main")

    def test_front_matter_is_not_left_in_the_embedded_text(self):
        """这是"不拆头"最直接的危害：YAML 字段进了 chunk 正文去做 embedding。"""
        with TemporaryDirectory() as tmp:
            path = self._write(tmp, "crawled.md", CRAWLED_MD)
            docs = documents_from_file(path)

        text = docs[0].get_content()
        self.assertNotIn("source_url:", text)
        self.assertNotIn("content_hash:", text)
        self.assertIn("根据教育部有关文件要求", text)

    def test_publish_date_wins_over_file_mtime_for_last_updated(self):
        """对抓回来的语料，"这篇通知哪天发的"远比"文件哪天落盘的"有意义——
        后者全是抓取当天，完全没有区分度，做不了时效性过滤。"""
        with TemporaryDirectory() as tmp:
            path = self._write(tmp, "crawled.md", CRAWLED_MD)
            docs = documents_from_file(path)

        self.assertEqual(docs[0].metadata["last_updated"], "2026-08-05")

    def test_plain_file_still_falls_back_to_mtime(self):
        """没有 front-matter 的普通语料行为必须完全不变（不能回归）。"""
        with TemporaryDirectory() as tmp:
            path = self._write(tmp, "plain.txt", "图书馆开馆时间 8:00-22:00")
            docs = documents_from_file(path)

        meta = docs[0].metadata
        self.assertEqual(meta["file_name"], "plain.txt")
        self.assertRegex(meta["last_updated"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertNotIn("source_url", meta)

    def test_doc_id_is_derived_from_body_not_including_front_matter(self):
        """doc_id 是内容 sha256，增量去重靠它。如果把 front-matter 也算进去，
        ``crawled_at`` 每次抓取都变 -> doc_id 每次都变 -> UPSERTS 永远判定
        "这是新文档"，增量摄取彻底失效。"""
        second_crawl = CRAWLED_MD.replace(
            "crawled_at: '2026-08-08T06:32:46+00:00'",
            "crawled_at: '2026-09-01T10:00:00+00:00'",
        )
        with TemporaryDirectory() as tmp:
            first = documents_from_file(self._write(tmp, "a.md", CRAWLED_MD))
            second = documents_from_file(self._write(tmp, "b.md", second_crawl))

        self.assertEqual(first[0].doc_id, second[0].doc_id)


if __name__ == "__main__":
    unittest.main()
