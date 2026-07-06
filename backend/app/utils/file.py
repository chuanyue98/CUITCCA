import os
import tempfile
from datetime import datetime
from io import BytesIO

import pandas as pd
from fastapi import UploadFile

from configs.load_env import PROJECT_ROOT, FEEDBACK_PATH
from models.user import Feedback


def get_folders_list(root_dir: str) -> list:
    folders_list = []
    dir = os.path.join(PROJECT_ROOT, root_dir)
    for dirpath, dirnames, filenames in os.walk(dir):
        for dirname in dirnames:
            folders_list.append(dirname)
    return folders_list


def save_feedback_to_file(feedback: Feedback, client_ip: str):
    current_datetime = datetime.now()
    filename = current_datetime.strftime("%Y-%m-%d_%H-%M-%S.txt")
    path = os.path.join(FEEDBACK_PATH, filename)
    os.makedirs(FEEDBACK_PATH, exist_ok=True)
    with open(path, "a", encoding="utf-8") as file:
        file.write(f"Name (IP): {client_ip}\n")
        file.write(f"Email: {feedback.email if feedback.email else 'NONE'}\n")
        file.write(f"Message: {feedback.message}\n")
        file.write("\n")


def read_file_contents(file: UploadFile) -> str:
    ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''

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
        content = contents.decode('utf-8')

    return ' '.join(content.split())
