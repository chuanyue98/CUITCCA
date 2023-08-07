import os

import pandas as pd

from configs.load_env import PROJECT_ROOT


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

if __name__ == '__main__':
    print(PROJECT_ROOT)
