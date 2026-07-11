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


if __name__ == '__main__':
    unittest.main()
