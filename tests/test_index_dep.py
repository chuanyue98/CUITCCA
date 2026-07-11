import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

import tests._pathsetup  # noqa: F401


class GetIndexTest(unittest.TestCase):
    def setUp(self):
        self._patcher = patch('dependencies.index_dep.get_index_by_name')
        self.mock_get_index_by_name = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_get_index_returns_index_when_found(self):
        from dependencies.index_dep import get_index
        fake_index = MagicMock()
        self.mock_get_index_by_name.return_value = fake_index
        result = get_index('my-index')
        self.mock_get_index_by_name.assert_called_once_with('my-index')
        self.assertIs(result, fake_index)

    def test_get_index_raises_400_when_not_found(self):
        from dependencies.index_dep import get_index
        self.mock_get_index_by_name.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            get_index('nonexistent')
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, 'index not exist')


if __name__ == '__main__':
    unittest.main()