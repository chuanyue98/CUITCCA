import asyncio
import os

from configs.load_env import PROJECT_ROOT, db_path
from fastapi import UploadFile
from handlers.parsers import ParseStatus, parse_bytes
from handlers.parsers.types import DocumentParseError, ParserUnavailableError
from models.user import Feedback
from utils import db


def safe_filename(filename: str) -> str:
    """
    去除路径分隔符，只保留文件名本身，防止路径穿越（如 ../../etc/passwd）
    """
    name = os.path.basename(filename.replace('\\', '/'))
    if name in ('', '.', '..'):
        raise ValueError(f'invalid filename: {filename!r}')
    return name


def get_folders_list(root_dir: str) -> list:
    folders_list = []
    dir = os.path.join(PROJECT_ROOT, root_dir)
    for dirpath, dirnames, filenames in os.walk(dir):
        for dirname in dirnames:
            folders_list.append(dirname)
    return folders_list


async def save_feedback(client_ip: str, feedback: Feedback):
    await asyncio.to_thread(db.save_feedback, db_path, client_ip, feedback.email, feedback.message)


def _read_file_sync(file: UploadFile) -> str:
    """同步读取上传文件的纯文本内容（用于 run_in_executor 包装）。

    解析本身全部委托给 ``handlers/parsers`` 注册表——这个函数以前自己实现了
    一遍 docx/pdf/xlsx 的解析分支，和生产摄取链路
    （``ingestion_pipeline.documents_from_file``）里经 SimpleDirectoryReader
    的那一套是**两份互相独立、行为还不一致**的实现（比如这边的 docx 分支只读
    段落、不读表格）。现在两条链路共用同一个注册表，格式支持和解析质量的改进
    只需要做一次。

    这里传 ``bytes`` 而不是落盘后传路径：上传内容本来就只在内存里，为了复用
    解析器再多绕一次临时文件的写入/删除没有意义（原实现的 docx 分支正是这么
    做的，还得配 try/finally 清理）。注册表的 ``parse_bytes`` 入口就是为这条
    链路准备的。

    返回值保持原有契约：**空白归一化后的单块文本**（原实现最后那句
    ``' '.join(content.split())``）。调用方 ``/index/{name}/upload_file_by_QA``
    要把它切块喂给 LLM 生成问答对，不需要保留排版。
    """
    filename = file.filename or ''
    ext = os.path.splitext(filename)[1].lower()
    result = parse_bytes(ext, file.file.read())

    if not result.ok:
        # parse_bytes 保证不抛异常、总是返回 ParseResult，但这条链路的调用方
        # 期望的是"解析不了就报错"（原实现里 pdfplumber/openpyxl 解析失败时
        # 异常会直接往上冒）。这里把失败结局重新转成异常，保持对上层的行为
        # 一致；用 parsers 自己的异常类型而不是裸 Exception，方便上层需要时
        # 区分"缺可选依赖"（ParserUnavailableError）和"文件本身有问题"。
        error_cls = ParserUnavailableError if result.status is ParseStatus.UNAVAILABLE else DocumentParseError
        raise error_cls(f"解析 {filename!r} 失败: {result.reason}")

    return ' '.join(result.text.split())


async def read_file_contents(file: UploadFile) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _read_file_sync, file)
