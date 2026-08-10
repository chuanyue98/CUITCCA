"""站点配置的加载与校验：把 ``sites.yaml`` 解析成类型化的配置对象。

这是"配置驱动"设计的核心——新增一个栏目/站点只需要改 YAML，不碰
``web_connector.py`` 的代码。本模块只负责"YAML -> 数据类"，不做任何网络
请求，纯函数、无副作用，方便单测覆盖各种配置形态（缺字段、非法 type 等）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

# sites.yaml 默认路径：和本模块同目录。允许调用方（CLI/测试）传别的路径覆盖，
# 但绝大多数场景下"用包自带的默认配置"就是正确行为。
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "sites.yaml"

SectionType = Literal["static", "listing"]


class ConfigError(ValueError):
    """配置文件格式错误（缺必填字段/字段类型不对/type 取值非法）。用专门的
    异常类型而不是裸 ValueError，方便调用方（CLI）区分"配置写错了"和其他
    运行期错误，给出更友好的提示。"""


@dataclass
class SectionConfig:
    """一个栏目的抓取规则。

    ``type="static"``：栏目本身就是若干篇固定页面（比如"学校简介"），
    ``urls`` 直接是要抓的详情页相对路径列表，没有分页概念。

    ``type="listing"``：栏目是一个可分页的文章列表（比如"通知公告"），需要
    先抓列表页拿到详情页链接，再逐篇抓正文。分页规律见
    ``web_connector.resolve_listing_page_url`` 的说明——第 1 页是
    ``list_first_page``，第 2 页起用 ``list_page_pattern`` 配合"倒序编号"
    还原实际 URL，编号总数从页面自身的翻页控件解析（不需要在配置里手填，见
    ``total_pages`` 字段说明），也可以显式在配置里写死作为 fallback。
    """

    name: str
    category: str
    type: SectionType
    title: str | None = None
    urls: list[str] = field(default_factory=list)
    list_first_page: str | None = None
    list_page_pattern: str | None = None
    total_pages: int | None = None
    """列表总页数。留空（None）时由 ``WebConnector`` 在抓到第 1 页后自动从
    翻页控件里解析（CUIT 站群 CMS 的列表页固定带"当前页/总页数"标记，见
    ``extract.discover_total_pages``），显式填写只是作为解析失败时的
    fallback，或者用于跳过一次网络请求的性能优化。"""


@dataclass
class SiteConfig:
    """一个站点（一个域名）下的全部栏目配置，以及站点级的礼貌抓取参数覆盖。"""

    name: str
    base_url: str
    display_name: str = ""
    enabled: bool = True
    sections: list[SectionConfig] = field(default_factory=list)
    user_agent: str | None = None
    request_interval_seconds: float | None = None
    max_concurrency: int | None = None
    timeout_seconds: float | None = None
    max_retries: int | None = None
    retry_backoff_seconds: float | None = None
    detail_content_selector: str | None = None
    detail_title_selector: str | None = None
    detail_date_selector: str | None = None
    list_item_selector: str | None = None
    default_max_pages: int | None = None
    disabled_reason: str | None = None
    """``enabled=False`` 时的原因说明，写进配置供人读，也会在 CLI 里打印
    出来提醒使用者这个站点当前没在抓——而不是让人以为"配置漏写了"。"""


@dataclass
class CrawlDefaults:
    """跨站点共享的默认礼貌抓取参数，站点/栏目可以逐项覆盖。"""

    user_agent: str
    request_interval_seconds: float
    max_concurrency: int
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    detail_content_selector: str
    detail_title_selector: str
    detail_date_selector: str
    list_item_selector: str
    default_max_pages: int


@dataclass
class ConnectorsConfig:
    defaults: CrawlDefaults
    sites: list[SiteConfig]

    def get_site(self, name: str) -> SiteConfig | None:
        return next((s for s in self.sites if s.name == name), None)


_REQUIRED_DEFAULTS_KEYS = (
    "user_agent",
    "request_interval_seconds",
    "max_concurrency",
    "timeout_seconds",
    "max_retries",
    "retry_backoff_seconds",
    "detail_content_selector",
    "detail_title_selector",
    "detail_date_selector",
    "list_item_selector",
    "default_max_pages",
)


def _parse_defaults(raw: dict[str, Any]) -> CrawlDefaults:
    missing = [k for k in _REQUIRED_DEFAULTS_KEYS if k not in raw]
    if missing:
        raise ConfigError(f"sites.yaml 的 defaults 缺少必填字段: {missing}")
    return CrawlDefaults(**{k: raw[k] for k in _REQUIRED_DEFAULTS_KEYS})


def _parse_section(raw: dict[str, Any], site_name: str) -> SectionConfig:
    name = raw.get("name")
    category = raw.get("category")
    section_type = raw.get("type")
    if not name or not category or not section_type:
        raise ConfigError(
            f"站点 {site_name!r} 的栏目配置缺少必填字段 name/category/type: {raw}"
        )
    if section_type not in ("static", "listing"):
        raise ConfigError(
            f"站点 {site_name!r} 栏目 {name!r} 的 type 只能是 static/listing，实际是 {section_type!r}"
        )
    section = SectionConfig(
        name=name,
        category=category,
        type=section_type,
        title=raw.get("title"),
        urls=list(raw.get("urls") or []),
        list_first_page=raw.get("list_first_page"),
        list_page_pattern=raw.get("list_page_pattern"),
        total_pages=raw.get("total_pages"),
    )
    if section.type == "static" and not section.urls:
        raise ConfigError(f"站点 {site_name!r} 栏目 {name!r} 是 static 类型但没有配置 urls")
    if section.type == "listing" and not (section.list_first_page and section.list_page_pattern):
        raise ConfigError(
            f"站点 {site_name!r} 栏目 {name!r} 是 listing 类型但缺少 "
            "list_first_page/list_page_pattern"
        )
    return section


def _parse_site(raw: dict[str, Any]) -> SiteConfig:
    name = raw.get("name")
    base_url = raw.get("base_url")
    if not name or not base_url:
        raise ConfigError(f"站点配置缺少必填字段 name/base_url: {raw}")
    sections = [_parse_section(s, name) for s in raw.get("sections") or []]
    return SiteConfig(
        name=name,
        base_url=base_url.rstrip("/"),
        display_name=raw.get("display_name", name),
        enabled=raw.get("enabled", True),
        sections=sections,
        user_agent=raw.get("user_agent"),
        request_interval_seconds=raw.get("request_interval_seconds"),
        max_concurrency=raw.get("max_concurrency"),
        timeout_seconds=raw.get("timeout_seconds"),
        max_retries=raw.get("max_retries"),
        retry_backoff_seconds=raw.get("retry_backoff_seconds"),
        detail_content_selector=raw.get("detail_content_selector"),
        detail_title_selector=raw.get("detail_title_selector"),
        detail_date_selector=raw.get("detail_date_selector"),
        list_item_selector=raw.get("list_item_selector"),
        default_max_pages=raw.get("default_max_pages"),
        disabled_reason=raw.get("disabled_reason"),
    )


def load_config(path: str | Path | None = None) -> ConnectorsConfig:
    """加载并校验 sites.yaml。``path`` 为空时用包内默认路径。"""
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise ConfigError(f"配置文件不存在: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if "defaults" not in raw or "sites" not in raw:
        raise ConfigError("sites.yaml 必须包含顶层的 defaults 和 sites 两个字段")

    defaults = _parse_defaults(raw["defaults"])
    sites = [_parse_site(s) for s in raw["sites"]]

    names = [s.name for s in sites]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ConfigError(f"sites.yaml 里存在重复的站点名: {duplicates}")

    return ConnectorsConfig(defaults=defaults, sites=sites)


def effective_value(site_value: Any, default_value: Any) -> Any:
    """站点级覆盖优先，否则回退到 defaults。抽成一个函数只是为了在
    ``web_connector.py`` 里避免到处写 ``x if x is not None else y`` 的重复
    三元表达式。"""
    return site_value if site_value is not None else default_value
