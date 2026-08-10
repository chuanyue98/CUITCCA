"""表格 -> Markdown 文本的小工具，pdf/docx/pptx 解析器共用。

只做最朴素的事情：把"行的列表，每行是单元格字符串列表"渲染成 GFM 风格的
Markdown 表格。不追求还原合并单元格、样式这些 pdfplumber/python-docx 本来
就不总能可靠还原的信息——目标是让表格的行列结构在纯文本里能被"看出来"，
供检索/LLM 消费，而不是像 ``extract_text()`` 那样把整张表塌成一行流水账。
"""
from __future__ import annotations


def rows_to_markdown(rows: list[list[str | None]]) -> str:
    """把二维单元格数组渲染成 Markdown 表格。

    - 空单元格（``None``）渲染成空字符串。
    - 单元格内部的换行/竖线会破坏 Markdown 表格语法，统一替换掉。
    - 第一行当表头；只有一行时，仍然补一行分隔线，保证输出是合法的 Markdown
      表格（有表头没数据行本身是合法的）。
    - 空输入（没有行，或每行都是空）返回空字符串，调用方应该跳过，不要拼出
      一个只有表头分隔线的空表格。
    """
    cleaned = [
        [_clean_cell(cell) for cell in row]
        for row in rows
        if any(_clean_cell(cell) for cell in row)
    ]
    if not cleaned:
        return ""

    n_cols = max(len(row) for row in cleaned)
    padded = [row + [""] * (n_cols - len(row)) for row in cleaned]

    header = padded[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * n_cols) + " |",
    ]
    for row in padded[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _clean_cell(cell: str | None) -> str:
    if cell is None:
        return ""
    return str(cell).replace("\n", " ").replace("|", "/").strip()
