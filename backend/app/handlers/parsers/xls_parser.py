""".xls（旧版 Excel 二进制格式）：用 xlrd 逐 sheet 逐行提取。

xlrd 从 2.0 起明确只支持 .xls，不再支持 .xlsx（这也是它和 openpyxl 分工
明确、可以放心按扩展名分派给两个不同解析器的原因——不用担心 xlrd 误吃了
.xlsx 文件）。

日期单元格特殊处理：xlrd 把日期存成"从某个纪元起的天数浮点数"
（``XL_CELL_DATE``），原样转字符串是一串没有意义的浮点数，用
``xldate_as_datetime`` 配合 ``workbook.datemode``（1900 还是 1904 纪元，两种
历史遗留都存在）还原成可读日期。
"""
from __future__ import annotations

import xlrd
from xlrd.xldate import XLDateError, xldate_as_datetime

from ._source import Source, read_all_bytes
from .types import ParseResult


def _cell_text(cell: xlrd.sheet.Cell, datemode: int) -> str:
    if cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_BLANK:
        return ""
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            dt = xldate_as_datetime(cell.value, datemode)
            return dt.date().isoformat() if dt.time().isoformat() == "00:00:00" else dt.isoformat(sep=" ")
        except (XLDateError, ValueError):
            return str(cell.value)
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        # 整数值不带 ".0" 尾巴，读起来更像原始表格里的样子（电话号码、编号等）
        value = cell.value
        return str(int(value)) if value == int(value) else str(value)
    return str(cell.value).strip()


def parse_xls(source: Source) -> ParseResult:
    raw = read_all_bytes(source)
    try:
        wb = xlrd.open_workbook(file_contents=raw)
    except Exception as e:
        return ParseResult.failure(f"{type(e).__name__}: {e}")

    texts: list[str] = []
    for sheet in wb.sheets():
        lines = [f"# {sheet.name}"]
        for r in range(sheet.nrows):
            cells = [_cell_text(sheet.cell(r, c), wb.datemode) for c in range(sheet.ncols)]
            cells = [c for c in cells if c]
            if cells:
                lines.append(" | ".join(cells))
        if len(lines) > 1:
            texts.append("\n".join(lines))

    return ParseResult.success(texts)
