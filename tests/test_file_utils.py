import unittest

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

import utils.file as f


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


if __name__ == '__main__':
    unittest.main()
