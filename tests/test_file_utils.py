import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import utils.file as f

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


class SafeFilenameTest(unittest.TestCase):
    def test_strips_posix_path_traversal(self):
        self.assertEqual(f.safe_filename('../../etc/passwd'), 'passwd')

    def test_strips_windows_path_traversal(self):
        self.assertEqual(f.safe_filename('..\\..\\windows\\win.ini'), 'win.ini')

    def test_strips_leading_absolute_path(self):
        self.assertEqual(f.safe_filename('/etc/passwd'), 'passwd')

    def test_keeps_plain_filename(self):
        self.assertEqual(f.safe_filename('report.pdf'), 'report.pdf')

    def test_rejects_empty_result(self):
        with self.assertRaises(ValueError):
            f.safe_filename('../')

    def test_rejects_dot_result(self):
        with self.assertRaises(ValueError):
            f.safe_filename('.')

    def test_rejects_double_dot_result(self):
        with self.assertRaises(ValueError):
            f.safe_filename('..')

    def test_rejects_empty_string(self):
        with self.assertRaises(ValueError):
            f.safe_filename('')

    def test_handles_filename_with_spaces(self):
        self.assertEqual(f.safe_filename('my report.pdf'), 'my report.pdf')

    def test_handles_mixed_separators(self):
        self.assertEqual(f.safe_filename('a/b\\c/d.txt'), 'd.txt')


class GetFoldersListTest(unittest.TestCase):
    @patch('utils.file.os.walk')
    @patch('utils.file.os.path.join', side_effect=lambda *args: '/'.join(args))
    @patch('utils.file.PROJECT_ROOT', '/fake/root')
    def test_returns_folder_names(self, mock_join, mock_walk):
        mock_walk.return_value = [
            ('/fake/root/data', ['sub1', 'sub2'], []),
        ]
        result = f.get_folders_list('data')
        self.assertEqual(result, ['sub1', 'sub2'])

    @patch('utils.file.os.walk')
    @patch('utils.file.os.path.join', side_effect=lambda *args: '/'.join(args))
    @patch('utils.file.PROJECT_ROOT', '/fake/root')
    def test_returns_empty_list_when_no_folders(self, mock_join, mock_walk):
        mock_walk.return_value = [
            ('/fake/root/data', [], []),
        ]
        result = f.get_folders_list('data')
        self.assertEqual(result, [])


class SaveFeedbackToFileTest(unittest.TestCase):
    @patch('utils.file.os.makedirs')
    @patch('utils.file.aiofiles.open')
    @patch('utils.file.datetime')
    @patch('utils.file.FEEDBACK_PATH', '/fake/feedback')
    def test_writes_feedback_with_all_fields(self, mock_datetime, mock_aio_open, mock_makedirs):
        mock_datetime.now.return_value.strftime.return_value = '2024-01-15_10-30-00.txt'
        mock_file = AsyncMock()
        mock_aio_open.return_value.__aenter__.return_value = mock_file

        feedback = MagicMock()
        feedback.email = 'test@example.com'
        feedback.message = 'Great tool!'

        asyncio.run(f.save_feedback_to_file(feedback, '192.168.1.1'))

        mock_makedirs.assert_called_once_with('/fake/feedback', exist_ok=True)
        mock_file.write.assert_any_call("Name (IP): 192.168.1.1\n")
        mock_file.write.assert_any_call("Email: test@example.com\n")
        mock_file.write.assert_any_call("Message: Great tool!\n")

    @patch('utils.file.os.makedirs')
    @patch('utils.file.aiofiles.open')
    @patch('utils.file.datetime')
    @patch('utils.file.FEEDBACK_PATH', '/fake/feedback')
    def test_writes_feedback_without_email(self, mock_datetime, mock_aio_open, mock_makedirs):
        mock_datetime.now.return_value.strftime.return_value = '2024-01-15_10-30-00.txt'
        mock_file = AsyncMock()
        mock_aio_open.return_value.__aenter__.return_value = mock_file

        feedback = MagicMock()
        feedback.email = None
        feedback.message = 'No email provided'

        asyncio.run(f.save_feedback_to_file(feedback, '10.0.0.1'))

        mock_file.write.assert_any_call("Email: NONE\n")


if __name__ == '__main__':
    unittest.main()
