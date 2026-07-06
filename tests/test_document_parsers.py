import unittest
from unittest.mock import MagicMock, patch
from io import BytesIO
from fastapi import UploadFile

import tests._pathsetup  # noqa: F401
from utils.file import read_file_contents

class DocumentParsersTest(unittest.TestCase):
    @patch('utils.file.tempfile.NamedTemporaryFile')
    @patch('utils.file.os.unlink')
    @patch('docx.Document')
    def test_docx_parser(self, mock_document_class, mock_unlink, mock_temp):
        mock_doc = MagicMock()
        p1 = MagicMock()
        p1.text = "Hello World."
        p2 = MagicMock()
        p2.text = "This is a docx test."
        mock_doc.paragraphs = [p1, p2]
        mock_document_class.return_value = mock_doc

        mock_temp_file = MagicMock()
        mock_temp_file.name = "fake.docx"
        mock_temp.return_value.__enter__.return_value = mock_temp_file

        fake_file = UploadFile(filename="test.docx", file=BytesIO(b"fake docx content"))

        content = read_file_contents(fake_file)
        self.assertEqual(content, "Hello World. This is a docx test.")
        mock_document_class.assert_called_once_with("fake.docx")

    @patch('pdfplumber.open')
    def test_pdf_parser(self, mock_pdf_open):
        mock_pdf = MagicMock()
        page1 = MagicMock()
        page1.extract_text.return_value = "Hello PDF page 1."
        page2 = MagicMock()
        page2.extract_text.return_value = "Hello PDF page 2."
        mock_pdf.pages = [page1, page2]
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf

        fake_file = UploadFile(filename="test.pdf", file=BytesIO(b"fake pdf content"))

        content = read_file_contents(fake_file)
        self.assertEqual(content, "Hello PDF page 1.Hello PDF page 2.")

    def test_txt_parser_utf8(self):
        fake_file = UploadFile(filename="test.txt", file=BytesIO("你好 UTF-8".encode("utf-8")))
        content = read_file_contents(fake_file)
        self.assertEqual(content, "你好 UTF-8")

    def test_txt_parser_gbk(self):
        fake_file = UploadFile(filename="test.txt", file=BytesIO("你好 GBK".encode("gbk")))
        content = read_file_contents(fake_file)
        self.assertEqual(content, "你好 GBK")

if __name__ == '__main__':
    unittest.main()
