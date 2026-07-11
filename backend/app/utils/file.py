import asyncio
import os
import tempfile
from datetime import datetime
from io import BytesIO

import aiofiles
from fastapi import UploadFile

from configs.load_env import PROJECT_ROOT, FEEDBACK_PATH
from models.user import Feedback


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


async def save_feedback_to_file(feedback: Feedback, client_ip: str):
    current_datetime = datetime.now()
    filename = current_datetime.strftime("%Y-%m-%d_%H-%M-%S.txt")
    path = os.path.join(FEEDBACK_PATH, filename)
    os.makedirs(FEEDBACK_PATH, exist_ok=True)
    async with aiofiles.open(path, "a", encoding="utf-8") as file:
        await file.write(f"Name (IP): {client_ip}\n")
        await file.write(f"Email: {feedback.email if feedback.email else 'NONE'}\n")
        await file.write(f"Message: {feedback.message}\n")
        await file.write("\n")


def _read_file_sync(file: UploadFile) -> str:
    """同步读取文件内容（用于 run_in_executor 包装）"""
    filename = file.filename or ''
    ext = filename.split('.')[-1].lower() if '.' in filename else ''

    if ext == 'docx':
        from docx import Document
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(file.file.read())
        try:
            doc = Document(temp_path)
            content_parts = []
            for paragraph in doc.paragraphs:
                content_parts.append(paragraph.text)
            content = ' '.join(content_parts)
        finally:
            os.unlink(temp_path)

    elif ext == 'pdf':
        import pdfplumber
        with pdfplumber.open(BytesIO(file.file.read())) as pdf:
            content = ''
            for page in pdf.pages:
                page_text = page.extract_text() or ''
                content = content + page_text
    else:
        contents = file.file.read()
        try:
            content = contents.decode('utf-8')
        except UnicodeDecodeError:
            content = contents.decode('gbk')

    return ' '.join(content.split())


async def read_file_contents(file: UploadFile) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read_file_sync, file)
