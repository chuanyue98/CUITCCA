"""每个解析器的输入统一是 ``Path | bytes``：

- ``Path``：生产摄取链路（``ingestion_pipeline.documents_from_file``）用的，
  文件已经落盘。
- ``bytes``：上传/QA 生成链路（``utils/file.py.read_file_contents``）用的，
  内容只在内存里（``UploadFile``），没必要为了复用解析器额外落一次盘。

各个第三方库（pdfplumber/python-docx/openpyxl/python-pptx/olefile）基本都
同时支持"路径字符串"和"file-like 对象"两种入参，所以解析器内部按类型分支
一次即可，不需要为两条链路各写一份实现——这正是"消除重复实现"的关键。
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

Source = Path | bytes


def as_path_or_stream(source: Source) -> str | BytesIO:
    """转成第三方库能直接吃的入参：``Path`` -> 字符串路径，``bytes`` ->
    ``BytesIO``（可重复 seek，多数库内部会 seek(0) 或多次读取）。"""
    if isinstance(source, Path):
        return str(source)
    return BytesIO(source)


def read_all_bytes(source: Source) -> bytes:
    """需要原始字节的解析器（olefile/xlrd 的 file_contents=、bs4、纯文本解码）
    用这个统一取字节，不用关心调用方传的是路径还是内存内容。"""
    if isinstance(source, Path):
        return source.read_bytes()
    return source
