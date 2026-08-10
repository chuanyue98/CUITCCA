"""``backend/app/connectors`` 的单元测试：配置解析、正文抽取、增量状态、
礼貌抓取（限速/重试/robots）、语料落盘。

全部不联网——网络请求用 fake httpx client，限速/重试用注入的假时钟和假
sleep。连接器的价值恰恰在于"抓取行为是否规矩"（间隔够不够、失败退避对不对、
robots 认不认），这些如果只能靠真的去打对方服务器来验证，就没法在 CI 里跑，
也没法在改动后快速回归。
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from connectors.base import CrawledDocument
from connectors.config import ConfigError, load_config
from connectors.extract import (
    discover_total_pages,
    extract_listing_items,
    extract_page,
    table_to_markdown,
)
from connectors.markdown_io import (
    parse_front_matter,
    render_markdown,
    sanitize_filename_component,
    stable_filename,
    write_markdown_file,
)
from connectors.rate_limit import IntervalRateLimiter, RetryExhaustedError, call_with_retry
from connectors.robots import RobotsChecker
from connectors.state import CrawlState

import tests._pathsetup  # noqa: F401


def _fake_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class StableFilenameTest(unittest.TestCase):
    def test_same_url_always_maps_to_same_filename(self):
        """增量覆盖的前提：同一 URL 必须落到同一个文件。"""
        url = "https://www.cuit.edu.cn/info/1006/16903.htm"
        self.assertEqual(stable_filename(url), stable_filename(url))

    def test_different_urls_do_not_collide(self):
        a = stable_filename("https://www.cuit.edu.cn/info/1006/16903.htm")
        b = stable_filename("https://www.cuit.edu.cn/info/1006/16904.htm")
        self.assertNotEqual(a, b)

    def test_filename_does_not_depend_on_title(self):
        """标题被编辑改一个字（比如加"【已结束】"前缀）不能产生新文件，
        否则旧文件变成永远不会更新的孤儿，同一页面在语料库里留下两个版本。"""
        url = "https://www.cuit.edu.cn/info/1006/16903.htm"
        name = stable_filename(url)
        self.assertNotIn("通知", name)
        self.assertTrue(name.endswith(".md"))

    def test_sanitize_strips_illegal_path_characters(self):
        cleaned = sanitize_filename_component('a/b:c*d?e"f<g>h|i j')
        for ch in '/:*?"<>| ':
            self.assertNotIn(ch, cleaned)

    def test_sanitize_never_returns_empty(self):
        self.assertTrue(sanitize_filename_component("///"))


class MarkdownIoTest(unittest.TestCase):
    def _doc(self, **overrides) -> CrawledDocument:
        base = dict(
            source_url="https://www.cuit.edu.cn/info/1006/16903.htm",
            title="关于2026年度本科专业拟设置情况的公示",
            category="通知公告",
            site="main",
            content_markdown="正文内容\n\n| 列A | 列B |\n| --- | --- |\n| 1 | 2 |",
            publish_date="2026-08-05",
            crawled_at="2026-08-08T06:32:46+00:00",
            content_hash="a" * 64,
        )
        base.update(overrides)
        return CrawledDocument(**base)  # type: ignore[arg-type]

    def test_front_matter_round_trip_preserves_provenance(self):
        """溯源 metadata 是知识库的核心资产（检索过滤 + 回答引用都靠它），
        写进去再读出来必须一模一样。"""
        doc = self._doc()
        fm, body = parse_front_matter(render_markdown(doc))
        self.assertEqual(fm["source_url"], doc.source_url)
        self.assertEqual(fm["title"], doc.title)
        self.assertEqual(fm["publish_date"], doc.publish_date)
        self.assertEqual(fm["category"], doc.category)
        self.assertEqual(fm["site"], doc.site)
        self.assertEqual(fm["content_hash"], doc.content_hash)
        self.assertIn("正文内容", body)

    def test_missing_publish_date_stays_null_not_crawl_time(self):
        """解析不到发布日期时必须诚实留空。用抓取时间冒充会污染下游"按时效性
        排序/过滤"的判断——一篇 2018 年的老政策会看起来像今天刚发的。"""
        fm, _ = parse_front_matter(render_markdown(self._doc(publish_date=None)))
        self.assertIsNone(fm["publish_date"])

    def test_table_structure_survives_round_trip(self):
        _, body = parse_front_matter(render_markdown(self._doc()))
        self.assertIn("| --- | --- |", body)

    def test_rewriting_same_url_overwrites_instead_of_duplicating(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            p1 = write_markdown_file(self._doc(), out)
            p2 = write_markdown_file(self._doc(content_markdown="更新后的正文"), out)
            self.assertEqual(p1, p2)
            self.assertEqual(len(list(out.glob("*.md"))), 1)
            self.assertIn("更新后的正文", p2.read_text(encoding="utf-8"))


class CrawlStateTest(unittest.TestCase):
    def test_unchanged_content_is_detected(self):
        with TemporaryDirectory() as tmp:
            state = CrawlState.load(Path(tmp) / "s.json")
            state.record("u1", content_hash="h1", output_path="a.md", crawled_at="t")
            self.assertTrue(state.is_unchanged("u1", "h1"))
            self.assertFalse(state.is_unchanged("u1", "h2"))
            self.assertFalse(state.is_unchanged("unknown", "h1"))

    def test_state_survives_save_and_reload(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            state = CrawlState.load(path)
            state.record("u1", content_hash="h1", output_path="a.md", crawled_at="t", title="标题")
            state.save()

            reloaded = CrawlState.load(path)
            self.assertTrue(reloaded.loaded_from_disk)
            self.assertTrue(reloaded.is_unchanged("u1", "h1"))
            self.assertEqual(len(reloaded), 1)

    def test_corrupt_state_file_degrades_to_full_crawl_instead_of_crashing(self):
        """状态文件损坏时退化成全量抓取是可接受的降级；直接崩掉不是。"""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text("{ this is not json", encoding="utf-8")
            state = CrawlState.load(path)
            self.assertFalse(state.loaded_from_disk)
            self.assertEqual(len(state), 0)

    def test_save_is_atomic_and_leaves_no_tmp_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            state = CrawlState.load(path)
            state.record("u1", content_hash="h", output_path="a.md", crawled_at="t")
            state.save()
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["s.json"])
            json.loads(path.read_text(encoding="utf-8"))  # 必须是完整合法 JSON


class RateLimitTest(unittest.TestCase):
    def test_interval_is_enforced_between_requests(self):
        slept: list[float] = []
        limiter = IntervalRateLimiter(1.5, sleep=slept.append)
        clock = iter([100.0, 100.2, 100.2])
        limiter._clock = lambda: next(clock)  # type: ignore[method-assign]

        limiter.wait()  # 首次不等待
        limiter.wait()  # 距上次仅 0.2s，应补足到 1.5s

        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], 1.3, places=6)

    def test_first_request_is_not_delayed(self):
        slept: list[float] = []
        IntervalRateLimiter(2.0, sleep=slept.append).wait()
        self.assertEqual(slept, [])

    def test_retry_stops_after_success(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("boom")
            return "ok"

        result = call_with_retry(
            flaky, max_retries=3, backoff_seconds=0.1,
            retry_on=(httpx.ConnectError,), sleep=lambda _: None,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 3)

    def test_backoff_grows_exponentially(self):
        slept: list[float] = []

        def always_fail():
            raise httpx.ConnectError("boom")

        with self.assertRaises(RetryExhaustedError):
            call_with_retry(
                always_fail, max_retries=3, backoff_seconds=1.0,
                retry_on=(httpx.ConnectError,), sleep=slept.append, jitter=0.0,
            )
        self.assertEqual(slept, [1.0, 2.0, 4.0])

    def test_unexpected_exception_is_not_retried(self):
        """只对网络类异常重试。把"代码写错了"当网络抖动反复重试，只会把一个
        本该立刻暴露的 bug 拖成一次缓慢的失败。"""
        calls = {"n": 0}

        def bug():
            calls["n"] += 1
            raise ValueError("这是代码 bug，不是网络问题")

        with self.assertRaises(ValueError):
            call_with_retry(
                bug, max_retries=3, backoff_seconds=0.1,
                retry_on=(httpx.ConnectError,), sleep=lambda _: None,
            )
        self.assertEqual(calls["n"], 1)


class RobotsTest(unittest.TestCase):
    def test_disallowed_path_is_blocked(self):
        def handler(request):
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")

        checker = RobotsChecker(_fake_client(handler), "TestBot/1.0")
        self.assertFalse(checker.is_allowed("https://x.edu.cn/private/secret.htm"))
        self.assertTrue(checker.is_allowed("https://x.edu.cn/public/ok.htm"))

    def test_missing_robots_txt_allows_crawling(self):
        """CUIT 官网实测就是这种情况（/robots.txt 返回 404）。"""
        checker = RobotsChecker(_fake_client(lambda r: httpx.Response(404)), "TestBot/1.0")
        self.assertTrue(checker.is_allowed("https://www.cuit.edu.cn/xygk/xxjj.htm"))

    def test_network_error_fails_open_rather_than_blocking_whole_site(self):
        """一次网络抖动不该误伤整站抓取；真正的访问失败会在抓正文时体现。"""
        def handler(request):
            raise httpx.ConnectError("network down")

        checker = RobotsChecker(_fake_client(handler), "TestBot/1.0")
        self.assertTrue(checker.is_allowed("https://x.edu.cn/a.htm"))

    def test_robots_txt_is_fetched_once_per_host(self):
        hits = {"n": 0}

        def handler(request):
            hits["n"] += 1
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")

        checker = RobotsChecker(_fake_client(handler), "TestBot/1.0")
        for i in range(5):
            checker.is_allowed(f"https://x.edu.cn/page{i}.htm")
        self.assertEqual(hits["n"], 1)


LISTING_HTML = """
<html><body>
<div class="pages">共2881条 <span class="p_t">1/193</span></div>
<ul class="list">
  <li><a href="../info/1006/16903.htm" title="关于2026年度本科专业拟设置情况的公示">
      <h3>关于2026年度本科专业拟设置情况的公示</h3><span>2026-08-05</span></a></li>
  <li><a href="../info/1006/16897.htm" title="2026年公开选调工作人员考试总成绩公告">
      <span>2026-08-03</span></a></li>
</ul>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<nav>导航菜单</nav>
<div class="article">
  <h2 class="tit">图书借还规则</h2>
  <p class="conttime">日期：2026-08-05</p>
  <div class="v_news_content">
    <p>读者凭本校一卡通借阅图书。</p>
    <table>
      <tr><td>读者类型</td><td>册数</td><td>借期</td></tr>
      <tr><td>本科生</td><td>10册</td><td>一个月</td></tr>
      <tr><td>硕士生</td><td>15册</td><td>二个月</td></tr>
    </table>
  </div>
</div>
<footer>版权所有</footer>
<script>var a=1;</script>
</body></html>
"""


class ExtractTest(unittest.TestCase):
    def test_listing_items_are_parsed_with_absolute_urls(self):
        items = extract_listing_items(LISTING_HTML, "https://www.cuit.edu.cn/index", "ul.list li a[href]")
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0].url.startswith("https://www.cuit.edu.cn/"))
        self.assertIn("16903.htm", items[0].url)
        self.assertEqual(items[0].publish_date, "2026-08-05")

    def test_listing_prefers_title_attribute_over_inner_text(self):
        """标签内文本常被内部 <h3> 的换行/空白污染，title 属性更干净。"""
        items = extract_listing_items(LISTING_HTML, "https://www.cuit.edu.cn/index", "ul.list li a[href]")
        self.assertEqual(items[0].title, "关于2026年度本科专业拟设置情况的公示")

    def test_total_pages_is_discovered_from_pager(self):
        self.assertEqual(discover_total_pages(LISTING_HTML), 193)

    def test_total_pages_returns_none_when_absent(self):
        self.assertIsNone(discover_total_pages("<html><body>没有翻页控件</body></html>"))

    def test_detail_page_extracts_title_date_and_body(self):
        page = extract_page(
            DETAIL_HTML,
            content_selector_csv="div.v_news_content, div.article",
            title_selector_csv="h2.tit, h1",
            date_selector_csv="p.conttime",
        )
        assert page is not None
        self.assertEqual(page.title, "图书借还规则")
        self.assertEqual(page.publish_date, "2026-08-05")
        self.assertIn("一卡通", page.content_markdown)

    def test_detail_page_preserves_table_structure(self):
        """借阅规则这类内容本质是表格，塌成一行就丢了"哪类读者对应哪个册数"。"""
        page = extract_page(
            DETAIL_HTML,
            content_selector_csv="div.v_news_content",
            title_selector_csv="h2.tit",
            date_selector_csv="p.conttime",
        )
        assert page is not None
        self.assertIn("| 读者类型 | 册数 | 借期 |", page.content_markdown)
        self.assertIn("| 本科生 | 10册 | 一个月 |", page.content_markdown)

    def test_navigation_and_scripts_are_stripped(self):
        page = extract_page(
            DETAIL_HTML,
            content_selector_csv="div.article",
            title_selector_csv="h2.tit",
            date_selector_csv="p.conttime",
        )
        assert page is not None
        self.assertNotIn("导航菜单", page.content_markdown)
        self.assertNotIn("var a", page.content_markdown)

    def test_unmatched_selector_falls_back_to_body_instead_of_dropping_page(self):
        """个别页面模板和主流程不一致时，宁可产出精度稍差的文档，也不要整篇丢弃。"""
        page = extract_page(
            "<html><body><div class='weird'><p>某个改版页面的正文</p></div></body></html>",
            content_selector_csv="div.v_news_content",
            title_selector_csv="h2.tit",
            date_selector_csv="p.conttime",
            fallback_title="兜底标题",
        )
        assert page is not None
        self.assertIn("某个改版页面的正文", page.content_markdown)

    def test_empty_page_returns_none_so_caller_can_treat_as_failure(self):
        self.assertIsNone(
            extract_page(
                "<html><body></body></html>",
                content_selector_csv="div.v_news_content",
                title_selector_csv="h2.tit",
                date_selector_csv="p.conttime",
            )
        )

    def test_table_to_markdown_handles_ragged_rows(self):
        from bs4 import BeautifulSoup
        html = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>"
        table = BeautifulSoup(html, "lxml").find("table")
        md = table_to_markdown(table)  # type: ignore[arg-type]
        self.assertIn("| a | b |", md)
        self.assertIn("| c |", md)


class ConfigTest(unittest.TestCase):
    def test_real_sites_config_loads(self):
        """仓库里那份 sites.yaml 必须始终可解析——它是连接器的唯一配置源。"""
        config = load_config()
        self.assertTrue(config.sites)
        names = {s.name for s in config.sites}
        self.assertIn("main", names)
        self.assertTrue(config.defaults.user_agent)

    def test_user_agent_is_ascii_only(self):
        """HTTP header 值不允许非 ASCII——曾经这里写了中文说明，一发请求就
        UnicodeEncodeError 直接崩。这条测试防止再次踩坑。"""
        load_config().defaults.user_agent.encode("ascii")

    def test_user_agent_identifies_the_bot_and_contact(self):
        ua = load_config().defaults.user_agent
        self.assertIn("CUITCCA", ua)
        self.assertIn("http", ua.lower())

    def test_polite_defaults_are_actually_polite(self):
        d = load_config().defaults
        self.assertGreaterEqual(d.request_interval_seconds, 0.5)
        self.assertLessEqual(d.max_concurrency, 4)

    def test_invalid_config_raises_config_error(self):
        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.yaml"
            bad.write_text("sites: 这不是一个列表\n", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(bad)


if __name__ == "__main__":
    unittest.main()
