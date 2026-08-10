"""解析结果的统一类型：核心原则是"永远不静默跳过"。

一个文件的解析结局只有三种，且必须显式表达出来，不允许用 try/except 吞掉
第三种（"能力不可用"）而伪装成第一种或第二种：

- ``SUCCESS``：解析成功，``texts`` 里是提取出的文本（通常 1 个元素；像 xlsx
  多 sheet 这种"一个文件天然对应多个逻辑文档"的场景允许多个，保留调用方按
  "一文件一 Document"还是"一 sheet 一 Document"切分的自由度，语义见各 parser
  模块）。
- ``FAILURE``：明确失败，比如文件损坏、格式不符合预期、依赖库解析时抛异常。
  ``reason`` 必须说清楚失败原因，调用方（ingestion_pipeline.ingest_files）会
  把它汇总进 ``IngestResult.parse_failures``，最终暴露给运维/使用者。
- ``UNAVAILABLE``：不是文件的问题，是这台机器缺少解析这种格式需要的可选依赖
  （目前只有 OCR）。``reason`` 里要给出明确的安装方式，不能让调用方以为文件
  本身有问题。

三种结局共用一个类型而不是"成功返回 str、失败抛异常"，是因为调用方
（``registry.parse_path``）需要能同时区分"根本没装 OCR"和"这张图片本身就
是空白/损坏"——两者都表现为"没有可用文本"，但处理方式完全不同（前者应该
提示装依赖，后者应该提示文件有问题），用单一的异常类型或者单一的"空字符
串"都无法把这个区别传递出去。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ParseStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNAVAILABLE = "unavailable"


@dataclass
class ParseResult:
    """单个文件的解析结果。构造请优先用 ``success``/``failure``/``unavailable``
    这几个工厂方法，不要直接摆弄 ``status``，避免忘记配套字段。"""

    status: ParseStatus
    texts: list[str] = field(default_factory=list)
    reason: str = ""
    degraded: bool = False
    """尽力而为的启发式提取（目前只有 .doc 的 piece table 解析）。``True`` 时
    ``reason`` 用来说明降级点在哪、可能丢失什么，调用方应该把它写进 metadata
    /日志，而不是假装这份文本和其它格式一样可信。"""

    @property
    def ok(self) -> bool:
        return self.status is ParseStatus.SUCCESS

    @property
    def text(self) -> str:
        """多数调用方（比如 utils/file.py 的 QA 生成场景）只需要一整块文本，
        不关心内部按什么粒度切分——这里统一用空行拼接返回。"""
        return "\n\n".join(self.texts)

    @classmethod
    def success(cls, texts: str | list[str], *, degraded: bool = False, reason: str = "") -> ParseResult:
        if isinstance(texts, str):
            texts = [texts]
        return cls(status=ParseStatus.SUCCESS, texts=texts, reason=reason, degraded=degraded)

    @classmethod
    def failure(cls, reason: str) -> ParseResult:
        return cls(status=ParseStatus.FAILURE, reason=reason)

    @classmethod
    def unavailable(cls, reason: str) -> ParseResult:
        return cls(status=ParseStatus.UNAVAILABLE, reason=reason)


class DocumentParseError(Exception):
    """文档解析明确失败（``ParseStatus.FAILURE``）。

    ``ingestion_pipeline.documents_from_file`` 用它把 ``ParseResult`` 的失败
    结局重新包装成异常抛出——这样 ``ingest_files`` 里已有的
    ``try/except Exception`` 不用改动就能继续把失败收进 ``parse_failures``，
    不用另起一套错误处理路径（见模块顶部说明"复用已有的 parse_failures"）。
    """


class ParserUnavailableError(DocumentParseError):
    """解析能力不可用（``ParseStatus.UNAVAILABLE``），比如 OCR 依赖未安装。

    单独成子类是为了让调用方（如果需要）可以用
    ``except ParserUnavailableError`` 把"缺依赖"和"文件真的解析失败"区分
    开——目前 ``ingest_files`` 没有区分对待，两者都进 ``parse_failures``，
    但保留这个区分点方便未来调用方（比如想在 UI 上提示"装个 OCR 依赖"）。
    """
