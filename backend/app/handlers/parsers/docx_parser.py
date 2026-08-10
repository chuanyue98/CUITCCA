""".docx：用 python-docx 按文档原始顺序抽取段落与表格。

## 为什么不用 docx2txt（生产链路以前用的是它，经 SimpleDirectoryReader）

生产摄取链路（``ingestion_pipeline.documents_from_file``）以前通过
``SimpleDirectoryReader`` 间接用 ``docx2txt``；QA 生成上传链路
（``utils/file.py._read_file_sync``）自己用 python-docx 但只读段落、不读
表格。两条路径各用一套实现，这是被明确要求消除的重复。统一成 python-docx
是因为：

1. python-docx 已经是本项目的直接依赖（``docx2txt`` 只是 llama_index reader
   的隐式依赖），用直接依赖更可控。
2. python-docx 能拿到文档的原始 XML 结构，可以按"段落/表格在文档里出现的
   先后顺序"依次抽取（见 ``_iter_block_items``），docx2txt 是黑盒转换，做
   不到"表格穿插在正文中间"这种场景下保留相对位置。
3. 表格转成 Markdown（复用 ``markdown_table.rows_to_markdown``），和 pdf/pptx
   解析器保持同一种表格表达方式，下游（分块/检索/LLM）不用适配三种不同格式。

## 已知取舍

不处理页眉页脚、批注、修订标记、文本框（这些通常不是正文核心内容）；
嵌套表格（表格单元格里还有表格）只取最外层单元格的纯文本，不递归展开——
这批语料里没有观察到嵌套表格，真遇到了会退化成"单元格文本里看不出内部
表格结构"而不是抛异常。
"""
from __future__ import annotations

from docx import Document as DocxDocument
from docx.document import Document as _DocxDocumentType
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from ._source import Source, as_path_or_stream
from .markdown_table import rows_to_markdown
from .types import ParseResult


def _iter_block_items(parent: _DocxDocumentType):
    """按文档原始顺序遍历顶层段落与表格。改编自 python-docx 官方文档给出的
    "iterate block items" 配方（该库本身没有暴露这种混合遍历的公开 API）。"""
    parent_elm = parent.element.body
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _table_rows(table: Table) -> list[list[str | None]]:
    rows = []
    for row in table.rows:
        rows.append([cell.text for cell in row.cells])
    return rows


def parse_docx(source: Source) -> ParseResult:
    try:
        doc = DocxDocument(as_path_or_stream(source))
    except Exception as e:
        return ParseResult.failure(f"{type(e).__name__}: {e}")

    parts: list[str] = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                parts.append(text)
        else:  # Table
            md = rows_to_markdown(_table_rows(block))
            if md:
                parts.append(md)

    return ParseResult.success("\n\n".join(parts))
