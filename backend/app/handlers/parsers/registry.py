"""按扩展名分派到具体解析器。新增一种格式只需要在 ``_PARSERS`` 里加一行，
不需要改这个模块里的任何分派逻辑——这是"可扩展"的全部含义。

两个公开入口对应两条调用链路（都在模块顶部 docstring 提到的两个消费者）：

- ``parse_path(path)``：生产摄取链路用，文件已经在磁盘上
  （``ingestion_pipeline.documents_from_file``）。
- ``parse_bytes(ext, data)``：上传/QA 生成链路用，内容只在内存里
  （``utils/file.py.read_file_contents``），不为了复用解析器多绕一次落盘。

两个入口都保证"不抛异常、总是返回 ``ParseResult``"——包括解析器实现里没
预料到的异常也会在这里被兜住转成 ``ParseResult.failure``，这样调用方
（不管是生产链路还是上传链路）都不需要在分派这一层再包一次 try/except，
只有各自的业务逻辑需要处理失败结局时才处理。
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ._source import Source
from .csv_parser import parse_csv
from .doc_parser import parse_doc
from .docx_parser import parse_docx
from .html_parser import parse_html
from .image_parser import parse_image
from .pdf_parser import parse_pdf
from .pptx_parser import parse_pptx
from .text_parser import parse_text
from .types import ParseResult
from .xls_parser import parse_xls
from .xlsx_parser import parse_xlsx

ParserFunc = Callable[[Source], ParseResult]

_PARSERS: dict[str, ParserFunc] = {
    ".txt": parse_text,
    ".md": parse_text,
    ".csv": parse_csv,
    ".docx": parse_docx,
    ".doc": parse_doc,
    ".xlsx": parse_xlsx,
    ".xls": parse_xls,
    ".pptx": parse_pptx,
    ".pdf": parse_pdf,
    ".html": parse_html,
    ".htm": parse_html,
    ".jpg": parse_image,
    ".jpeg": parse_image,
    ".png": parse_image,
}


def supported_extensions() -> frozenset[str]:
    return frozenset(_PARSERS)


def _dispatch(ext: str, source: Source) -> ParseResult:
    parser = _PARSERS.get(ext.lower())
    if parser is None:
        return ParseResult.failure(f"不支持的文件扩展名: {ext!r}")
    try:
        return parser(source)
    except Exception as e:
        # 各解析器内部已经各自 try/except 过预期内的错误（文件损坏、格式不
        # 符合预期等），能走到这里的是解析器实现里没预料到的异常——同样不能
        # 让它直接往上抛导致调用方（尤其是批量摄取场景）整个流程中断，转成
        # FAILURE 让调用方能继续处理其它文件，同时保留原始异常信息定位问题。
        return ParseResult.failure(f"解析器内部错误 {type(e).__name__}: {e}")


def parse_path(path: Path) -> ParseResult:
    return _dispatch(path.suffix, path)


def parse_bytes(ext: str, data: bytes) -> ParseResult:
    return _dispatch(ext, data)
