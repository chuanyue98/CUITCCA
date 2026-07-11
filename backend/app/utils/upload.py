import os

from configs.load_env import MAX_FILE_SIZE, ALLOWED_EXTENSIONS


class FileTooLargeError(Exception):
    pass


class InvalidFileTypeError(Exception):
    pass


def validate_upload_file(file) -> None:
    if file.size > MAX_FILE_SIZE:
        raise FileTooLargeError(f"文件大小 {file.size} 超过限制 {MAX_FILE_SIZE}")

    if not file.filename:
        raise InvalidFileTypeError("文件名称为空")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(f"文件类型 {ext} 不在允许列表中")
