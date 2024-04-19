import os
from datetime import datetime
from io import BytesIO

import pandas as pd
from fastapi import UploadFile

from configs.load_env import PROJECT_ROOT, FEEDBACK_PATH
from models.user import Feedback


def xlsx_to_csv(input_file, output_file):
    # 读取XLSX文件
    data_frame = pd.read_excel(input_file)

    # 将数据保存为CSV文件
    data_frame.to_csv(output_file, index=False)


from docx import Document

def convert_doc_to_docx(doc_file, docx_file):
   doc = Document(doc_file)
   doc.save(docx_file)

def get_folders_list(root_dir: str) -> list:
    """
    遍历指定目录下的所有子目录，并将子目录名称存储在一个列表中返回。
    """
    folders_list = []
    dir = os.path.join(PROJECT_ROOT, root_dir)
    for dirpath, dirnames, filenames in os.walk(dir):
        for dirname in dirnames:
            folders_list.append(dirname)
    return folders_list


def save_feedback_to_file(feedback: Feedback, client_ip: str):
    # 获取当前的时间和日期
    current_datetime = datetime.now()

    # 生成文件名
    filename = current_datetime.strftime("%Y-%m-%d_%H-%M-%S.txt")
    path = os.path.join(FEEDBACK_PATH, filename)
    os.makedirs(FEEDBACK_PATH, exist_ok=True)
    # 打开文件，以追加模式写入数据
    with open(path, "a", encoding="utf-8") as file:
        file.write(f"Name (IP): {client_ip}\n")
        file.write(f"Email: {feedback.email if feedback.email else 'NONE'}\n")
        file.write(f"Message: {feedback.message}\n")
        file.write("\n")


def read_file_contents(file: UploadFile) -> str:
    # 获取文件扩展名
    ext = file.filename.split('.')[-1].lower()

    # 根据文件扩展名选择读取方法
    if ext == 'docx':
        from docx import Document
        import tempfile
        # 将 SpooledTemporaryFile 对象转换为临时文件对象
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(file.file.read())
            temp_file.seek(0)
            # 使用 python-docx 库读取 Word 文档
            doc = Document(temp_file)
            content_parts = []

            # 读取文档内容
            for paragraph in doc.paragraphs:
                content_parts.append(paragraph.text)

            # 将内容拼接为字符串
            content = ' '.join(content_parts)

    elif ext == 'pdf':
        import pdfplumber

        with pdfplumber.open(BytesIO(file.file.read())) as pdf:
            content = ''
            for i in range(len(pdf.pages)):
                # 读取PDF文档第i+1页
                page = pdf.pages[i]

                # page.extract_text()函数即读取文本内容，下面这步是去掉文档最下面的页码
                page_content = '\n'.join(page.extract_text().split('\n')[:-1])
                content = content + page_content
    else:
        # 默认使用 UTF-8 编码读取文件内容
        contents = file.file.read()
        content = contents.decode('utf-8')

    return ' '.join(content.split())


if __name__ == '__main__':
    print(PROJECT_ROOT)
