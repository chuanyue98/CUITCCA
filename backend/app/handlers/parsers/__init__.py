"""文档解析器注册表：按扩展名分派到具体格式的解析实现。

设计动机见 ``registry.py``、``types.py`` 模块 docstring。调用方（
``handlers/ingestion_pipeline.py`` 和 ``utils/file.py``）应该只依赖这里导出
的公开符号，不要直接 import 具体某个 ``xxx_parser`` 模块——分派逻辑集中在
``registry.py``，新增格式不应该要求调用方跟着改 import。
"""
from __future__ import annotations

from .registry import parse_bytes, parse_path, supported_extensions
from .types import DocumentParseError, ParseResult, ParserUnavailableError, ParseStatus

__all__ = [
    "DocumentParseError",
    "ParseResult",
    "ParseStatus",
    "ParserUnavailableError",
    "parse_bytes",
    "parse_path",
    "supported_extensions",
]
