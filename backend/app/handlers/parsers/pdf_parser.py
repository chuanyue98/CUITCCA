""".pdf：pdfplumber 同时做正文提取和表格提取，表格转成 Markdown 嵌入文本流。

## 去重策略：为什么不是简单地 extract_text() + extract_tables() 拼接

pdfplumber 的 ``page.extract_text()`` 是"这一页上所有字符按阅读顺序拼起来"，
它不知道、也不关心某些字符恰好落在一个表格的框线范围内——所以表格里的文字
本来就会出现在 ``extract_text()`` 的结果里，只是丢了行列结构（变成一行流水
账，这正是要解决的问题）。如果直接把 ``extract_text()`` 的结果和
``extract_tables()`` 转换出的 Markdown 表格简单拼接，表格内容会在文本里出现
两次：一次在正文流水账里，一次在 Markdown 表格里。

处理方式：先用 ``page.find_tables()`` 拿到这一页所有表格的边界框
（bbox），用 ``page.filter()`` 排除掉"中心点落在任意一个表格 bbox 内"的
字符/图形对象，剩下的对象再 ``extract_text()`` 得到"去掉表格内容之后的正文"
（``_prose_outside_tables``）；表格本身单独用 ``Table.extract()`` 拿行数据、
转成 Markdown。两部分拼在一起，表格内容只出现一次，而且是保留了行列结构的
Markdown 形式，不是塌成一行的流水账。

判断"字符是否落在表格内"用的是**字符包围盒的中心点**是否落在表格 bbox
内（而不是要求完全包含），实测在文字紧贴表格边框的情况下更不容易漏判
（完全包含判定容易因为 1-2px 的边框误差把边缘那一列文字误判成"表格外"，
导致它们既没进正文也没进表格提取——中心点判定基本不会有这个问题）。

## 已知局限

- 跨页表格（表头在上一页、数据延续到下一页）会被当成两个独立表格分别转成
  Markdown，各自都没有表头——pdfplumber 的 ``find_tables()`` 本身就是按页
  独立检测的，要处理跨页表格需要额外的"合并相邻页表格"逻辑，这批语料没有
  发现明显的跨页大表格，暂不处理。
- 表格检测基于线条/间距的启发式（pdfplumber 默认策略），扫描件/无框线的
  "视觉表格"可能检测不到，会退化成普通正文提取（不会报错，只是没有 Markdown
  结构化）。
"""
from __future__ import annotations

from typing import Any

import pdfplumber

from ._source import Source, as_path_or_stream
from .markdown_table import rows_to_markdown
from .types import ParseResult


def _bbox_center_inside(obj: dict[str, Any], bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    obj_x0 = obj.get("x0", 0.0)
    obj_x1 = obj.get("x1", obj_x0)
    obj_top = obj.get("top", 0.0)
    obj_bottom = obj.get("bottom", obj_top)
    cx = (obj_x0 + obj_x1) / 2
    cy = (obj_top + obj_bottom) / 2
    return x0 <= cx <= x1 and top <= cy <= bottom


def _extract_page(page: Any) -> str:
    tables = list(page.find_tables())
    if not tables:
        return page.extract_text() or ""

    bboxes = [t.bbox for t in tables]

    def _outside_all_tables(obj: dict[str, Any]) -> bool:
        return not any(_bbox_center_inside(obj, bbox) for bbox in bboxes)

    prose = page.filter(_outside_all_tables).extract_text() or ""
    table_blocks = [md for t in tables if (md := rows_to_markdown(t.extract()))]

    return "\n\n".join(part for part in [prose, *table_blocks] if part)


def parse_pdf(source: Source) -> ParseResult:
    try:
        with pdfplumber.open(as_path_or_stream(source)) as pdf:
            page_texts = [_extract_page(page) for page in pdf.pages]
    except Exception as e:
        return ParseResult.failure(f"{type(e).__name__}: {e}")

    text = "\n\n".join(t for t in page_texts if t)
    return ParseResult.success(text)
