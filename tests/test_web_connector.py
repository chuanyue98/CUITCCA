"""``connectors/web_connector.py``——连接器的编排层。

这是整个采集链路真正"做决策"的地方：什么时候跳过（robots / 404 / 内容没变）、
什么时候算失败、翻页翻到哪停、增量比对怎么生效。前面那些模块（extract / state /
rate_limit / robots）各自都好测，但它们**怎么被串起来**才是出错的高发区，也是
一次真实抓取里唯一会烧对方服务器带宽的部分。

全程用 ``httpx.MockTransport`` 假造响应，不联网、不 sleep（限速间隔设 0）。
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from connectors.base import SourceRef
from connectors.config import CrawlDefaults, SectionConfig, SiteConfig
from connectors.state import CrawlState
from connectors.web_connector import WebConnector

import tests._pathsetup  # noqa: F401

LIST_HTML = """
<html><body>
<span class="p_t">1/3</span>
<ul class="list">
  <li><a href="/info/1/101.htm" title="第一篇"><span>2026-08-05</span></a></li>
  <li><a href="/info/1/102.htm" title="第二篇"><span>2026-08-04</span></a></li>
</ul>
</body></html>
"""

LIST_HTML_PAGE2 = """
<html><body><ul class="list">
  <li><a href="/info/1/201.htm" title="第三篇"><span>2026-07-01</span></a></li>
</ul></body></html>
"""

DETAIL_HTML = """
<html><body><div class="article">
  <h2 class="tit">图书借还规则</h2>
  <p class="conttime">日期：2026-08-05</p>
  <div class="v_news_content"><p>读者凭本校一卡通借阅图书。</p></div>
</div></body></html>
"""

# 正文容器命中、但里面一个字都没有（内容全是海报图片）。实测主站"成信学术"
# 栏目（info/1007）就是这种情况，一次真实抓取里 72 篇报告预告全长这样。
#
# 注意这里刻意连标题文字都不放：``_select_first`` 会逐个试候选选择器并要求
# **非空文本**，只要页面上还有任何文字（哪怕只是标题），``div.article`` 这类
# 外层候选就会被选中、进而产出一篇内容稀薄但非空的文档。要复现"真的什么都
# 提取不到"这个分支，页面上必须确实没有可提取的文字。
IMAGE_ONLY_HTML = """
<html><body><div class="article">
<div class="v_news_content"><p><img src="/poster.jpg"/></p></div>
</div></body></html>
"""


def _defaults(**overrides) -> CrawlDefaults:
    base = dict(
        user_agent="TestBot/1.0",
        request_interval_seconds=0.0,  # 测试里不真的等
        max_concurrency=1,
        timeout_seconds=5.0,
        max_retries=2,
        retry_backoff_seconds=0.0,
        detail_content_selector="div.v_news_content, div.article",
        detail_title_selector="h2.tit",
        detail_date_selector="p.conttime",
        list_item_selector="ul.list li a[href]",
        default_max_pages=5,
    )
    base.update(overrides)
    return CrawlDefaults(**base)  # type: ignore[arg-type]


def _static_section() -> SectionConfig:
    return SectionConfig(name="xxjj", category="学校概况", type="static", urls=["/xygk/xxjj.htm"])


def _listing_section(**overrides) -> SectionConfig:
    base = dict(
        name="tzgg",
        category="通知公告",
        type="listing",
        list_first_page="/index/tzgg.htm",
        list_page_pattern="/index/tzgg/{n}.htm",
    )
    base.update(overrides)
    return SectionConfig(**base)  # type: ignore[arg-type]


def _site(sections, **overrides) -> SiteConfig:
    base = dict(name="main", base_url="https://x.edu.cn", sections=sections)
    base.update(overrides)
    return SiteConfig(**base)  # type: ignore[arg-type]


def _connector(handler, sections=None, **kwargs) -> WebConnector:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return WebConnector(
        site=_site(sections if sections is not None else [_static_section()]),
        defaults=_defaults(),
        client=client,
        **kwargs,
    )


def _routes(mapping: dict, default_status: int = 404):
    """按 path 分发的 MockTransport handler。robots.txt 一律 404（视为未声明限制）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(404)
        if path in mapping:
            value = mapping[path]
            if isinstance(value, int):
                return httpx.Response(value)
            if isinstance(value, Exception):
                raise value
            return httpx.Response(200, text=value)
        return httpx.Response(default_status)

    return handler


class ConstructionTest(unittest.TestCase):
    def test_disabled_site_is_rejected_loudly(self):
        """配置里 enabled: false 的站点（zjc 抓不通、ywtb 是 SPA）不该被静默
        构造出一个什么都抓不到的连接器。"""
        client = httpx.Client(transport=httpx.MockTransport(_routes({})))
        with self.assertRaises(ValueError) as ctx:
            WebConnector(
                site=_site([_static_section()], enabled=False, disabled_reason="网络不可达"),
                defaults=_defaults(),
                client=client,
            )
        self.assertIn("main", str(ctx.exception))

    def test_site_level_settings_override_defaults(self):
        client = httpx.Client(transport=httpx.MockTransport(_routes({})))
        conn = WebConnector(
            site=_site([_static_section()], timeout_seconds=99.0, detail_title_selector="h1.custom"),
            defaults=_defaults(),
            client=client,
        )
        self.assertEqual(conn.timeout, 99.0)
        self.assertEqual(conn.title_selector, "h1.custom")
        # 没覆盖的项继承 defaults
        self.assertEqual(conn.user_agent, "TestBot/1.0")


class FetchUrlBehaviourTest(unittest.TestCase):
    """``_fetch_url`` 是所有 GET 的唯一入口，四种结局要分得清清楚楚。"""

    def test_404_is_not_counted_as_failure(self):
        """分页场景下 404 往往只是"翻到底了"，算成失败会让统计变得没法看。"""
        conn = _connector(_routes({}))
        self.assertIsNone(conn._fetch_url("https://x.edu.cn/missing.htm"))
        self.assertEqual(conn.stats.failed, 0)

    def test_unexpected_status_is_counted_as_failure(self):
        conn = _connector(_routes({"/weird.htm": 403}))
        self.assertIsNone(conn._fetch_url("https://x.edu.cn/weird.htm"))
        self.assertEqual(conn.stats.failed, 1)

    def test_robots_disallow_is_counted_separately_from_failure(self):
        """"对方不让抓"和"抓失败了"是两回事，混在一起会误导排障方向。"""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
            return httpx.Response(200, text="ok")

        conn = _connector(handler)
        self.assertIsNone(conn._fetch_url("https://x.edu.cn/private/a.htm"))
        self.assertEqual(conn.stats.skipped_robots, 1)
        self.assertEqual(conn.stats.failed, 0)

    def test_server_error_is_retried_then_counted_as_failure(self):
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            attempts["n"] += 1
            return httpx.Response(503)

        conn = _connector(handler)
        self.assertIsNone(conn._fetch_url("https://x.edu.cn/flaky.htm"))
        # max_retries=2 -> 首次 + 2 次重试 = 3 次
        self.assertEqual(attempts["n"], 3)
        self.assertEqual(conn.stats.failed, 1)

    def test_transient_error_that_recovers_is_not_a_failure(self):
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx.Response(500)
            return httpx.Response(200, text="recovered")

        conn = _connector(handler)
        resp = conn._fetch_url("https://x.edu.cn/flaky.htm")
        assert resp is not None
        self.assertEqual(resp.text, "recovered")
        self.assertEqual(conn.stats.failed, 0)


class DiscoverTest(unittest.TestCase):
    def test_static_section_yields_configured_urls(self):
        conn = _connector(_routes({}), sections=[_static_section()])
        refs = list(conn.discover())
        self.assertEqual([r.identifier for r in refs], ["https://x.edu.cn/xygk/xxjj.htm"])
        self.assertEqual(refs[0].category, "学校概况")

    def test_listing_section_paginates_with_reverse_numbering(self):
        """分页是倒序编号：第 1 页是 tzgg.htm，第 2 页是 tzgg/{总页数-1}.htm。
        总页数从第 1 页的翻页控件解析（这里是 1/3）。"""
        conn = _connector(
            _routes({"/index/tzgg.htm": LIST_HTML, "/index/tzgg/2.htm": LIST_HTML_PAGE2}),
            sections=[_listing_section()],
            max_pages_override=2,
        )
        urls = [r.identifier for r in conn.discover()]
        self.assertIn("https://x.edu.cn/info/1/101.htm", urls)
        self.assertIn("https://x.edu.cn/info/1/201.htm", urls)

    def test_duplicate_urls_across_pages_are_yielded_once(self):
        conn = _connector(
            _routes({"/index/tzgg.htm": LIST_HTML, "/index/tzgg/2.htm": LIST_HTML}),
            sections=[_listing_section()],
            max_pages_override=2,
        )
        urls = [r.identifier for r in conn.discover()]
        self.assertEqual(len(urls), len(set(urls)))

    def test_listing_stops_when_a_page_has_no_items(self):
        conn = _connector(
            _routes({"/index/tzgg.htm": LIST_HTML, "/index/tzgg/2.htm": "<html><body>空</body></html>"}),
            sections=[_listing_section()],
            max_pages_override=3,
        )
        urls = [r.identifier for r in conn.discover()]
        self.assertEqual(len(urls), 2)  # 只有第 1 页的两条

    def test_listing_section_is_skipped_when_first_page_fails(self):
        """第 1 页都抓不到就别继续翻了，否则会对着一个坏栏目连发若干请求。"""
        conn = _connector(_routes({}), sections=[_listing_section()], max_pages_override=3)
        self.assertEqual(list(conn.discover()), [])

    def test_max_pages_zero_yields_nothing_without_any_request(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(request.url.path)
            return httpx.Response(404)

        conn = _connector(handler, sections=[_listing_section()], max_pages_override=0)
        self.assertEqual(list(conn.discover()), [])
        self.assertEqual(requested, [])

    def test_section_names_filter_selects_subset(self):
        conn = _connector(
            _routes({"/index/tzgg.htm": LIST_HTML}),
            sections=[_static_section(), _listing_section()],
            section_names=["xxjj"],
        )
        refs = list(conn.discover())
        self.assertEqual([r.extra["section"] for r in refs], ["xxjj"])

    def test_listing_metadata_is_carried_on_the_ref(self):
        conn = _connector(
            _routes({"/index/tzgg.htm": LIST_HTML}),
            sections=[_listing_section()],
            max_pages_override=1,
        )
        ref = next(iter(conn.discover()))
        self.assertEqual(ref.extra["listing_title"], "第一篇")
        self.assertEqual(ref.extra["listing_date"], "2026-08-05")


class FetchTest(unittest.TestCase):
    def _ref(self, path="/info/1/101.htm", **extra) -> SourceRef:
        return SourceRef(
            identifier=f"https://x.edu.cn{path}", site="main", category="通知公告", extra=extra
        )

    def test_successful_fetch_produces_document_with_provenance(self):
        conn = _connector(_routes({"/info/1/101.htm": DETAIL_HTML}))
        doc = conn.fetch(self._ref())
        assert doc is not None
        self.assertEqual(doc.title, "图书借还规则")
        self.assertEqual(doc.publish_date, "2026-08-05")
        self.assertEqual(doc.category, "通知公告")
        self.assertEqual(doc.site, "main")
        self.assertIn("一卡通", doc.content_markdown)
        self.assertTrue(doc.content_hash)
        self.assertTrue(doc.crawled_at)
        self.assertEqual(conn.stats.fetched, 1)

    def test_image_only_page_is_a_failure_not_an_empty_document(self):
        """写一篇空文档进知识库比不写更糟——检索会命中一个什么都没有的条目。"""
        conn = _connector(_routes({"/info/1/101.htm": IMAGE_ONLY_HTML}))
        self.assertIsNone(conn.fetch(self._ref()))
        self.assertEqual(conn.stats.failed, 1)
        self.assertEqual(conn.stats.fetched, 0)

    def test_publish_date_falls_back_to_listing_date(self):
        """详情页解析不到日期时，用列表页上那个日期兜底，总比留空好。"""
        no_date = DETAIL_HTML.replace('<p class="conttime">日期：2026-08-05</p>', "")
        conn = _connector(_routes({"/info/1/101.htm": no_date}))
        doc = conn.fetch(self._ref(listing_date="2026-01-02"))
        assert doc is not None
        self.assertEqual(doc.publish_date, "2026-01-02")

    def test_publish_date_stays_none_when_nothing_is_known(self):
        """不能拿抓取时间冒充发布日期——会污染下游的时效性过滤。"""
        no_date = DETAIL_HTML.replace('<p class="conttime">日期：2026-08-05</p>', "")
        conn = _connector(_routes({"/info/1/101.htm": no_date}))
        doc = conn.fetch(self._ref())
        assert doc is not None
        self.assertIsNone(doc.publish_date)

    def test_title_falls_back_to_listing_title(self):
        no_title = DETAIL_HTML.replace('<h2 class="tit">图书借还规则</h2>', "")
        conn = _connector(_routes({"/info/1/101.htm": no_title}))
        doc = conn.fetch(self._ref(listing_title="列表页标题"))
        assert doc is not None
        self.assertEqual(doc.title, "列表页标题")


class IncrementalModeTest(unittest.TestCase):
    def _ref(self) -> SourceRef:
        return SourceRef(
            identifier="https://x.edu.cn/info/1/101.htm", site="main", category="通知公告", extra={}
        )

    def _conn(self, state, mode):
        return _connector(_routes({"/info/1/101.htm": DETAIL_HTML}), mode=mode, state=state)

    def test_unchanged_content_is_skipped_in_incremental_mode(self):
        with TemporaryDirectory() as tmp:
            state = CrawlState.load(Path(tmp) / "s.json")

            first = self._conn(state, "incremental").fetch(self._ref())
            assert first is not None
            state.record(
                first.source_url, content_hash=first.content_hash,
                output_path="a.md", crawled_at=first.crawled_at,
            )

            conn2 = self._conn(state, "incremental")
            self.assertIsNone(conn2.fetch(self._ref()))
            self.assertEqual(conn2.stats.skipped_unchanged, 1)
            self.assertEqual(conn2.stats.fetched, 0)

    def test_full_mode_refetches_even_when_unchanged(self):
        with TemporaryDirectory() as tmp:
            state = CrawlState.load(Path(tmp) / "s.json")
            first = self._conn(state, "incremental").fetch(self._ref())
            assert first is not None
            state.record(
                first.source_url, content_hash=first.content_hash,
                output_path="a.md", crawled_at=first.crawled_at,
            )

            conn2 = self._conn(state, "full")
            self.assertIsNotNone(conn2.fetch(self._ref()))
            self.assertEqual(conn2.stats.skipped_unchanged, 0)

    def test_changed_content_is_refetched(self):
        with TemporaryDirectory() as tmp:
            state = CrawlState.load(Path(tmp) / "s.json")
            state.record(
                "https://x.edu.cn/info/1/101.htm", content_hash="旧的hash",
                output_path="a.md", crawled_at="t",
            )
            conn = self._conn(state, "incremental")
            self.assertIsNotNone(conn.fetch(self._ref()))
            self.assertEqual(conn.stats.fetched, 1)

    def test_no_state_behaves_as_full_crawl(self):
        conn = _connector(_routes({"/info/1/101.htm": DETAIL_HTML}), mode="incremental", state=None)
        self.assertIsNotNone(conn.fetch(SourceRef(
            identifier="https://x.edu.cn/info/1/101.htm", site="main", category="c", extra={},
        )))


class RunOrchestrationTest(unittest.TestCase):
    def test_run_yields_only_documents_that_were_actually_produced(self):
        """``run()`` 串起 discover -> fetch，跳过的条目不该产出 None 混进结果。"""
        conn = _connector(
            _routes({
                "/index/tzgg.htm": LIST_HTML,
                "/info/1/101.htm": DETAIL_HTML,
                # 102 故意不配 -> 404 -> fetch 返回 None
            }),
            sections=[_listing_section()],
            max_pages_override=1,
        )
        docs = list(conn.run())
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].source_url, "https://x.edu.cn/info/1/101.htm")
        self.assertEqual(conn.stats.discovered, 2)
        self.assertEqual(conn.stats.fetched, 1)


if __name__ == "__main__":
    unittest.main()
