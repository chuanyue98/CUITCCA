""".txt / .md：纯文本，唯一的坑是编码。

语料里混杂 UTF-8 和 GBK（不同年代不同人导出的文档常见问题），策略是"优先
UTF-8，失败退 GBK"，和 ``utils/file.py`` 里原有的兜底分支保持一致——这里
统一成一个实现，两条链路都用它，不用各自维护一份同样的 try/except。
"""
from __future__ import annotations

from ._source import Source, read_all_bytes
from .types import ParseResult


def parse_text(source: Source) -> ParseResult:
    raw = read_all_bytes(source)
    if not raw:
        return ParseResult.success("")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError as e:
            return ParseResult.failure(f"既不是有效的 UTF-8 也不是有效的 GBK 编码: {e}")
    return ParseResult.success(text)
