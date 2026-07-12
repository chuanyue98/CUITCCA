import asyncio  # noqa: I001 (tests._pathsetup must precede models.user below)
import unittest
from unittest.mock import patch

import utils.file as f

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)
from models.user import Feedback


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


class SaveFeedbackTest(unittest.TestCase):
    def test_save_feedback_persists_to_sqlite(self):
        with patch('utils.file.db.save_feedback') as mock_save, \
             patch('utils.file.db_path', '/fake/app.db'):
            feedback = Feedback(email='a@b.com', message='hello')
            asyncio.run(f.save_feedback('192.168.1.1', feedback))
        mock_save.assert_called_once_with('/fake/app.db', '192.168.1.1', 'a@b.com', 'hello')


if __name__ == '__main__':
    unittest.main()
