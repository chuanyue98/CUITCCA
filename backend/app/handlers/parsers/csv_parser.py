""".csv：逐行读取，保留列结构（用 " | " 连接单元格，比直接丢给纯文本解码器
更可读，尤其是列数较多的表格型语料）。

不用 pandas（虽然项目已经依赖它）：csv 语料多是随手导出的表格，字段数不齐、
偶尔有坏行很常见，``csv.reader`` 逐行读、单行出错不影响其它行；pandas
``read_csv`` 默认按第一行推断列数，遇到不整齐的行容易直接抛异常整份文件
解析失败，对这批语料而言"尽量多提取几行"比"结构化更严格"更有价值。
"""
from __future__ import annotations

import csv
import io

from ._source import Source, read_all_bytes
from .types import ParseResult


def parse_csv(source: Source) -> ParseResult:
    raw = read_all_bytes(source)
    if not raw:
        return ParseResult.success("")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError as e:
            return ParseResult.failure(f"既不是有效的 UTF-8 也不是有效的 GBK 编码: {e}")

    lines = []
    for row in csv.reader(io.StringIO(text)):
        line = " | ".join(cell.strip() for cell in row if cell.strip())
        if line:
            lines.append(line)
    return ParseResult.success("\n".join(lines))
