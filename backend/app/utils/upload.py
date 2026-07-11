import os

from configs.load_env import ALLOWED_EXTENSIONS, MAX_FILE_SIZE


class FileTooLargeError(Exception):
    pass


class InvalidFileTypeError(Exception):
    pass


def validate_upload_file(file) -> None:
    file_size = file.size
    if file_size is not None and file_size > MAX_FILE_SIZE:
        raise FileTooLargeError(f"文件大小 {file_size} 超过限制 {MAX_FILE_SIZE}")

    if not file.filename:
        raise InvalidFileTypeError("文件名称为空")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(f"文件类型 {ext} 不在允许列表中")
