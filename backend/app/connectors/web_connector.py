"""Web 数据源的连接器实现：按配置驱动的规则枚举页面、抓取正文、产出标准化
文档。这是 ``BaseConnector`` 目前唯一的具体实现。

## discover() 里为什么会发网络请求

``BaseConnector.discover()`` 的抽象契约是"只枚举、不算真正抓取"，但对 Web
连接器来说，"知道一个可分页栏目下有哪些详情页 URL"这件事本身就需要先抓
列表页——这是网络爬虫固有的两阶段结构（列表页发现链接、详情页取正文），
不是对基类契约的破坏，只是"抓取"这个词在这里天然包含"抓列表页"和"抓详情页"
两类请求，两者都走同一套限速/重试/robots 检查（见 ``_fetch_url``），行为上
没有区别对待。

## 分页 URL 还原规则

CUIT 站群 CMS（www.cuit.edu.cn 及其共用同一模板的二级站点，见
``sites.yaml`` 头部注释里记录的实测结构）的列表分页是"倒序编号"：第 1 页是
不带编号的固定 URL（``list_first_page``），第 2 页开始文件名用总页数倒推：
第 i 页（i>=2）对应编号 ``n = total_pages - i + 1``，一直数到第
``total_pages`` 页对应 ``n = 1``。``total_pages`` 优先用配置里显式写的值，
留空则从第 1 页的翻页控件里自动解析（``extract.discover_total_pages``）。
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urljoin

import httpx
from connectors.base import BaseConnector, CrawledDocument, SourceRef
from connectors.config import CrawlDefaults, SectionConfig, SiteConfig, effective_value
from connectors.extract import discover_total_pages, extract_listing_items, extract_page
from connectors.rate_limit import IntervalRateLimiter, RetryExhaustedError, call_with_retry
from connectors.robots import RobotsChecker
from connectors.state import CrawlState

CrawlMode = Literal["incremental", "full"]

# 5xx（服务端瞬时错误）、连接失败、超时才重试；4xx 是"这个 URL 本身有问题"
# （不存在/无权限），重试没有意义，直接当结果处理。
_RETRYABLE_EXCEPTIONS = (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError)


@dataclass
class CrawlStats:
    """一次 WebConnector 运行的统计计数，供 CLI 汇总打印。

    **必须用 ``bump()`` 累加，不要直接 ``stats.x += 1``**：``scripts/crawl_cuit.py``
    把 ``connector.fetch`` 提交给 ``ThreadPoolExecutor``（默认 max_concurrency=2），
    而 ``+=`` 在 Python 里是"读-改-写"三步、不是原子操作，多线程下会丢更新。
    这些计数是使用者判断"这次抓取有没有悄悄漏掉页面"的**唯一**信号，少算一条
    就等于漏掉一次静默失败，所以哪怕只是统计也值得上锁（争用极低，代价可忽略）。
    """

    discovered: int = 0
    """discover() 产出、进入过 fetch() 的条目数（包含最终被跳过/失败的）。"""
    fetched: int = 0
    """成功产出新文档（真正会落盘）的数量。"""
    skipped_unchanged: int = 0
    """增量模式下，内容 hash 与上次一致而跳过的数量。"""
    skipped_robots: int = 0
    """被 robots.txt 拒绝而跳过的数量。"""
    failed: int = 0
    """请求失败（重试耗尽/非预期状态码/无可提取正文）的数量。"""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def bump(self, field_name: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, field_name, getattr(self, field_name) + amount)


def _join(base_url: str, relative: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", relative.lstrip("/"))


class WebConnector(BaseConnector):
    """一个站点的 Web 连接器实例。一个 ``SiteConfig`` 对应一个实例。"""

    def __init__(
        self,
        site: SiteConfig,
        defaults: CrawlDefaults,
        client: httpx.Client,
        *,
        mode: CrawlMode = "incremental",
        state: CrawlState | None = None,
        max_pages_override: int | None = None,
        section_names: set[str] | None = None,
        logger: logging.Logger | None = None,
    ):
        """
        :param mode: "incremental" 时，若 ``state`` 里记录的 hash 与本次抓到的
            正文 hash 一致则跳过（不产出文档）；"full" 时忽略 hash 比对，总是
            产出（仍然会更新 state，为下次增量做准备）。
        :param state: 增量状态存取对象。传 None 等价于强制全量（没有历史可比）。
        :param max_pages_override: 覆盖所有 listing 栏目的翻页深度（通常来自
            CLI ``--max-pages``），不传则用每个栏目/站点/全局 defaults 里配置的
            ``default_max_pages``。
        :param section_names: 只抓这些栏目（按 ``SectionConfig.name`` 过滤），
            不传则抓站点下全部启用的栏目。
        """
        if not site.enabled:
            raise ValueError(f"站点 {site.name!r} 在配置里被禁用（enabled: false），不应构造 WebConnector")

        self.name = site.name
        self.site = site
        self.defaults = defaults
        self.client = client
        self.mode = mode
        self.state = state
        self.max_pages_override = max_pages_override
        self.section_names = section_names
        self.logger = logger or logging.getLogger(f"connectors.web.{site.name}")

        self.user_agent = effective_value(site.user_agent, defaults.user_agent)
        self.timeout = effective_value(site.timeout_seconds, defaults.timeout_seconds)
        self.max_retries = effective_value(site.max_retries, defaults.max_retries)
        self.retry_backoff = effective_value(site.retry_backoff_seconds, defaults.retry_backoff_seconds)
        self.content_selector = effective_value(site.detail_content_selector, defaults.detail_content_selector)
        self.title_selector = effective_value(site.detail_title_selector, defaults.detail_title_selector)
        self.date_selector = effective_value(site.detail_date_selector, defaults.detail_date_selector)
        self.list_item_selector = effective_value(site.list_item_selector, defaults.list_item_selector)
        self.default_max_pages = effective_value(site.default_max_pages, defaults.default_max_pages)

        self.robots = RobotsChecker(client, self.user_agent, timeout_seconds=self.timeout)
        self.rate_limiter = IntervalRateLimiter(
            effective_value(site.request_interval_seconds, defaults.request_interval_seconds)
        )
        self.stats = CrawlStats()

    # ------------------------------------------------------------------
    # 底层请求：robots 检查 + 限速 + 重试，所有 GET 请求唯一入口
    # ------------------------------------------------------------------
    def _fetch_url(self, url: str) -> httpx.Response | None:
        if not self.robots.is_allowed(url):
            self.logger.warning("robots.txt 禁止抓取，跳过: %s", url)
            self.stats.bump("skipped_robots")
            return None

        def _attempt() -> httpx.Response:
            self.rate_limiter.wait()
            resp = self.client.get(url, timeout=self.timeout, headers={"User-Agent": self.user_agent})
            if resp.status_code >= 500:
                resp.raise_for_status()
            return resp

        try:
            resp = call_with_retry(
                _attempt,
                max_retries=self.max_retries,
                backoff_seconds=self.retry_backoff,
                retry_on=_RETRYABLE_EXCEPTIONS,
            )
        except RetryExhaustedError as e:
            self.logger.error("抓取失败（重试 %d 次后放弃）: %s -- %s", e.attempts, url, e.last_error)
            self.stats.bump("failed")
            return None

        if resp.status_code == 404:
            # 404 在分页场景下往往是"已经翻到底了"的正常信号，不算失败。
            self.logger.debug("404，跳过: %s", url)
            return None
        if resp.status_code != 200:
            self.logger.warning("非预期状态码 %d: %s", resp.status_code, url)
            self.stats.bump("failed")
            return None
        return resp

    # ------------------------------------------------------------------
    # discover: 枚举 SourceRef
    # ------------------------------------------------------------------
    def _enabled_sections(self) -> list[SectionConfig]:
        if self.section_names is None:
            return list(self.site.sections)
        return [s for s in self.site.sections if s.name in self.section_names]

    def discover(self) -> Iterator[SourceRef]:
        for section in self._enabled_sections():
            if section.type == "static":
                yield from self._discover_static(section)
            else:
                yield from self._discover_listing(section)

    def _discover_static(self, section: SectionConfig) -> Iterator[SourceRef]:
        for rel_url in section.urls:
            url = _join(self.site.base_url, rel_url)
            yield SourceRef(
                identifier=url, site=self.site.name, category=section.category, extra={"section": section.name}
            )

    def _resolve_max_pages(self, section: SectionConfig) -> int:
        if self.max_pages_override is not None:
            return self.max_pages_override
        return self.default_max_pages

    def _discover_listing(self, section: SectionConfig) -> Iterator[SourceRef]:
        assert section.list_first_page is not None
        assert section.list_page_pattern is not None

        max_pages = self._resolve_max_pages(section)
        if max_pages < 1:
            return

        first_url = _join(self.site.base_url, section.list_first_page)
        resp = self._fetch_url(first_url)
        if resp is None:
            self.logger.error("栏目 %s/%s 第 1 页抓取失败，跳过整个栏目", self.site.name, section.name)
            return

        total_pages = section.total_pages or discover_total_pages(resp.text) or 1
        effective_pages = min(max_pages, total_pages)

        seen_urls: set[str] = set()
        html = resp.text
        for page_index in range(1, effective_pages + 1):
            if page_index > 1:
                n = total_pages - page_index + 1
                if n < 1:
                    break
                page_url = _join(self.site.base_url, section.list_page_pattern.format(n=n))
                page_resp = self._fetch_url(page_url)
                if page_resp is None:
                    self.logger.warning(
                        "栏目 %s/%s 翻页在第 %d 页中断", self.site.name, section.name, page_index
                    )
                    break
                html = page_resp.text

            items = extract_listing_items(html, self.site.base_url, self.list_item_selector)
            if not items:
                self.logger.info(
                    "栏目 %s/%s 第 %d 页未解析到条目，停止翻页", self.site.name, section.name, page_index
                )
                break

            for item in items:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                yield SourceRef(
                    identifier=item.url,
                    site=self.site.name,
                    category=section.category,
                    extra={
                        "section": section.name,
                        "listing_title": item.title,
                        "listing_date": item.publish_date or "",
                    },
                )

    # ------------------------------------------------------------------
    # fetch: 抓详情页正文，产出标准化文档
    # ------------------------------------------------------------------
    def fetch(self, ref: SourceRef) -> CrawledDocument | None:
        self.stats.bump("discovered")
        resp = self._fetch_url(ref.identifier)
        if resp is None:
            return None

        listing_title = ref.extra.get("listing_title", "")
        page = extract_page(
            resp.text,
            content_selector_csv=self.content_selector,
            title_selector_csv=self.title_selector,
            date_selector_csv=self.date_selector,
            fallback_title=listing_title,
        )
        if page is None:
            # 措辞刻意区分两种情况：实测主站"成信学术"栏目（info/1007）有 70+
            # 篇报告预告，正文容器 div.v_news_content 是**命中**的，但里面只有
            # 一张海报 <img>、一个字都没有。之前统一报"正文选择器未命中"是误导
            # 的——会让人以为选择器配错了、跑去改配置，实际上配置没问题，是这
            # 些页面本来就没有可提取的文本（内容全在图片里）。
            # 两种情况都算 failed（都没产出文档），但排障方向完全不同。
            self.logger.warning(
                "无可提取正文（选择器未命中，或命中的容器内没有文字——"
                "比如整页内容是图片海报），跳过: %s",
                ref.identifier,
            )
            self.stats.bump("failed")
            return None

        title = page.title or listing_title or ref.identifier
        publish_date = page.publish_date or (ref.extra.get("listing_date") or None)
        content_hash = hashlib.sha256(page.content_markdown.encode("utf-8")).hexdigest()

        if self.mode == "incremental" and self.state is not None and self.state.is_unchanged(
            ref.identifier, content_hash
        ):
            self.stats.bump("skipped_unchanged")
            return None

        self.stats.bump("fetched")
        return CrawledDocument(
            source_url=ref.identifier,
            title=title,
            category=ref.category,
            site=ref.site,
            content_markdown=page.content_markdown,
            publish_date=publish_date,
            crawled_at=datetime.now(UTC).isoformat(timespec="seconds"),
            content_hash=content_hash,
        )
