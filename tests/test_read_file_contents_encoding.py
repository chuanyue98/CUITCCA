import io
import unittest

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

from fastapi import UploadFile

import utils.file as file_utils


class ReadFileContentsEncodingTest(unittest.TestCase):
    def test_decodes_gbk_encoded_text_files_instead_of_crashing(self):
        text = "成都信息工程大学图书馆开放时间"
        gbk_bytes = text.encode('gbk')
        upload = UploadFile(file=io.BytesIO(gbk_bytes), filename='note.txt')

        result = file_utils.read_file_contents(upload)

        self.assertIn("成都信息工程大学图书馆开放时间", result)

    def test_still_decodes_utf8_text_files(self):
        text = "hello 世界"
        upload = UploadFile(file=io.BytesIO(text.encode('utf-8')), filename='note.txt')

        result = file_utils.read_file_contents(upload)

        self.assertEqual(result, text)


if __name__ == '__main__':
    unittest.main()
