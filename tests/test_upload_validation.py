import unittest
from unittest.mock import MagicMock

from utils.upload import FileTooLargeError, InvalidFileTypeError, validate_upload_file

import tests._pathsetup  # noqa: F401


class UploadValidationTest(unittest.TestCase):
    def test_rejects_file_too_large(self):
        mock_file = MagicMock()
        mock_file.size = 20 * 1024 * 1024  # 20MB
        mock_file.filename = "test.pdf"

        with self.assertRaises(FileTooLargeError):
            validate_upload_file(mock_file)

    def test_accepts_pdf(self):
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.filename = "test.pdf"

        validate_upload_file(mock_file)  # should not raise

    def test_rejects_exe(self):
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.filename = "malware.exe"

        with self.assertRaises(InvalidFileTypeError):
            validate_upload_file(mock_file)

    def test_accepts_newly_supported_formats(self):
        """这几种格式原来被白名单挡掉，导致语料里 21% 的文件静默进不了知识库。"""
        for filename in ("表格.doc", "名单.xls", "流程.pptx", "页面.html", "流程图.jpg"):
            with self.subTest(filename=filename):
                mock_file = MagicMock()
                mock_file.size = 1024
                mock_file.filename = filename
                validate_upload_file(mock_file)  # 不应抛异常

    def test_still_rejects_json(self):
        """语料目录里的 json 是旧版 llama_index 持久化产物，不是知识内容，
        刻意不纳入白名单。"""
        mock_file = MagicMock()
        mock_file.size = 1024
        mock_file.filename = "docstore.json"

        with self.assertRaises(InvalidFileTypeError):
            validate_upload_file(mock_file)


class AllowedExtensionsConsistencyTest(unittest.TestCase):
    """白名单与解析器注册表的一致性约束。

    白名单是安全控制、注册表是能力声明，两者刻意分开维护（见
    configs/load_env.py 里的说明）。但有一个方向的约束必须始终成立：
    **能收就必须能解析**。否则会退回到改造前那种"文件收进来了，但没有任何
    解析器认识它"的状态——上传成功、内容却悄悄没进知识库。
    """

    def test_whitelist_is_subset_of_parsable_formats(self):
        import configs.load_env as load_env
        from handlers.parsers import supported_extensions

        unparsable = set(load_env.ALLOWED_EXTENSIONS) - set(supported_extensions())
        self.assertEqual(
            unparsable, set(),
            f"这些扩展名允许上传但没有对应解析器，会导致静默丢内容: {sorted(unparsable)}",
        )


if __name__ == '__main__':
    unittest.main()
