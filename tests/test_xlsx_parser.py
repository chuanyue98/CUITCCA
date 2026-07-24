"""XLSX 文件解析器测试：覆盖 utils/file.py 中新增的 openpyxl 读取逻辑。"""
import asyncio
import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from fastapi import UploadFile

import tests._pathsetup  # noqa: F401
from utils.file import read_file_contents


class XlsxParserTest(unittest.TestCase):
    @patch('openpyxl.load_workbook')
    def test_xlsx_parser_extracts_text_from_all_sheets(self, mock_load_wb):
        """XLSX 解析器应遍历所有工作表并提取非空行文本"""
        mock_ws1 = MagicMock()
        mock_ws1.iter_rows.return_value = [
            ("姓名", "年龄", "城市"),
            ("张三", 20, "成都"),
            ("李四", 22, "北京"),
        ]
        mock_ws2 = MagicMock()
        mock_ws2.iter_rows.return_value = [
            ("课程", "学分"),
            ("数据结构", 4),
        ]

        mock_wb = MagicMock()
        mock_wb.sheetnames = ['Sheet1', 'Sheet2']
        mock_wb.__getitem__ = lambda self, key: mock_ws1 if key == 'Sheet1' else mock_ws2
        mock_load_wb.return_value = mock_wb

        fake_file = UploadFile(filename="test.xlsx", file=BytesIO(b"fake xlsx content"))
        content = asyncio.run(read_file_contents(fake_file))

        self.assertIn("张三", content)
        self.assertIn("成都", content)
        self.assertIn("数据结构", content)
        self.assertIn("4", content)
        mock_load_wb.assert_called_once()
        mock_wb.close.assert_called_once()

    @patch('openpyxl.load_workbook')
    def test_xlsx_parser_skips_empty_rows(self, mock_load_wb):
        """XLSX 解析器应跳过空行"""
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [
            ("A", "B"),
            (None, None),
            ("C", "D"),
        ]

        mock_wb = MagicMock()
        mock_wb.sheetnames = ['Sheet1']
        mock_wb.__getitem__ = lambda self, key: mock_ws
        mock_load_wb.return_value = mock_wb

        fake_file = UploadFile(filename="data.xlsx", file=BytesIO(b"fake"))
        content = asyncio.run(read_file_contents(fake_file))

        self.assertIn("A", content)
        self.assertIn("C", content)
        # 空行不应产生额外的空格对
        parts = content.split()
        self.assertNotIn("", parts)

    @patch('openpyxl.load_workbook')
    def test_xlsx_parser_uses_read_only_and_data_only_mode(self, mock_load_wb):
        """XLSX 解析器应以 read_only=True, data_only=True 模式打开，避免加载公式和格式"""
        mock_wb = MagicMock()
        mock_wb.sheetnames = []
        mock_load_wb.return_value = mock_wb

        fake_file = UploadFile(filename="test.xlsx", file=BytesIO(b"fake"))
        asyncio.run(read_file_contents(fake_file))

        call_kwargs = mock_load_wb.call_args.kwargs
        self.assertTrue(call_kwargs.get('read_only'))
        self.assertTrue(call_kwargs.get('data_only'))

    @patch('openpyxl.load_workbook')
    def test_xlsx_parser_handles_none_cells(self, mock_load_wb):
        """XLSX 解析器应正确处理 None 值单元格"""
        mock_ws = MagicMock()
        mock_ws.iter_rows.return_value = [
            ("hello", None, "world"),
        ]

        mock_wb = MagicMock()
        mock_wb.sheetnames = ['Sheet1']
        mock_wb.__getitem__ = lambda self, key: mock_ws
        mock_load_wb.return_value = mock_wb

        fake_file = UploadFile(filename="test.xlsx", file=BytesIO(b"fake"))
        content = asyncio.run(read_file_contents(fake_file))

        self.assertIn("hello", content)
        self.assertIn("world", content)
        # None 不应出现在内容中
        self.assertNotIn("None", content)

    @patch('openpyxl.load_workbook')
    def test_xlsx_parser_handles_empty_workbook(self, mock_load_wb):
        """XLSX 解析器应处理空工作簿（无工作表）"""
        mock_wb = MagicMock()
        mock_wb.sheetnames = []
        mock_load_wb.return_value = mock_wb

        fake_file = UploadFile(filename="empty.xlsx", file=BytesIO(b"fake"))
        content = asyncio.run(read_file_contents(fake_file))

        self.assertEqual(content, "")


if __name__ == '__main__':
    unittest.main()
