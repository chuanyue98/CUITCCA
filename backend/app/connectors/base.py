"""连接器抽象基类与标准化产物数据结构。

设计目的：现在只有一个 Web 实现（``web_connector.WebConnector``），但校园知识
库未来大概率还要接教务系统 API、迎新数据库这类非 Web 数据源。把"发现有哪些
条目要抓"（``discover``）和"抓单个条目"（``fetch``）拆成两个抽象方法，是为了
让 ``run()`` 里的"遍历 + 产出标准文档"编排逻辑对所有数据源通用，新数据源只需
要实现这两个方法、不用重新写一遍限速/重试/落盘的胶水代码。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceRef:
    """``discover()`` 产出的"待抓取条目"引用，只携带定位信息，不含内容。

    对 Web 连接器来说这就是一个 URL；为将来非 Web 数据源留了 ``site``/
    ``category`` 之外的自由字段（``extra``），比如数据库连接器可以把主键塞进
    ``extra``。
    """

    identifier: str
    """条目的唯一定位符（Web 场景下是绝对 URL）。"""
    site: str
    """所属站点名（对应配置文件里的 ``sites[].name``）。"""
    category: str
    """业务分类/栏目名，直接写进最终文档 metadata 的 ``category``。"""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class CrawledDocument:
    """连接器产出的标准化文档：一篇正文 + 完整溯源 metadata。

    这些 metadata 字段是刻意固定的集合（不是"能抓到什么塞什么"），因为它们
    要在检索时用于过滤（比如"只查通知公告"）、在回答里做引用溯源（"来源于
    XX 页面，发布于 XX 日期"）——字段名和语义需要稳定，才能被下游摄取/检索
    代码依赖。
    """

    source_url: str
    """内容详情页的绝对 URL，唯一定位这篇文档，也是增量抓取判重的 key。"""
    title: str
    category: str
    """栏目/业务分类，来自配置文件（比如"通知公告"），不是从页面猜的——页面
    标题往往不能可靠反映栏目归属，配置里显式声明更可靠。"""
    site: str
    """站点名（如 "main"/"jwc"），对应配置文件 ``sites[].name``。"""
    content_markdown: str
    """正文（已去噪、表格转 Markdown），是最终写入语料文件 body 的内容。"""
    publish_date: str | None
    """从页面解析出的发布日期（ISO ``YYYY-MM-DD``），不是抓取时间。解析失败
    时为 ``None``——诚实反映"这篇页面没有可靠日期"，不用抓取时间冒充，避免
    污染下游"按时效性排序/过滤"的判断。"""
    crawled_at: str
    """本次抓取发生的时间（ISO 8601，UTC），用于区分"内容多新"和"我们多久前
    抓的"这两件不同的事。"""
    content_hash: str
    """正文 sha256，供增量抓取比对——同 URL 下次抓取算出同样的 hash 就跳过，
    见 ``state.CrawlState``。"""


class BaseConnector(ABC):
    """所有数据连接器的抽象基类。"""

    name: str

    @abstractmethod
    def discover(self) -> Iterable[SourceRef]:
        """枚举本次要抓取的条目引用。只做"列出有哪些东西"，不发起正文抓取——
        拆开这一步是为了让调用方能先看到"发现了 N 条"再决定要不要真的抓
        （dry-run 场景），也方便限速逻辑只作用于真正的抓取请求，不影响枚举。
        """

    @abstractmethod
    def fetch(self, ref: SourceRef) -> CrawledDocument | None:
        """抓取单个条目，返回标准化文档。返回 ``None`` 表示"本条目本次不产出
        文档"（比如内容未变化被增量逻辑跳过、或抓取失败且重试已耗尽）——由
        调用方决定这种情况下如何统计/报告，本方法不抛异常掩盖这类预期内的
        跳过。
        """

    def run(self) -> Iterator[CrawledDocument]:
        """默认编排：依次 discover -> fetch，产出非 None 的文档。子类一般不
        需要覆盖这个方法，除非要在 fetch 之间插入自己的编排逻辑（比如并发）。
        """
        for ref in self.discover():
            doc = self.fetch(ref)
            if doc is not None:
                yield doc
