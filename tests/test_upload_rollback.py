"""文件上传回滚测试：覆盖 router/index.py 中上传失败时的文件清理逻辑。"""
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import tests._pathsetup  # noqa: F401


def _load_index_module():
    """Load router/index.py standalone, bypassing router/__init__.py."""
    app_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app'
    )
    spec = importlib.util.spec_from_file_location(
        'router_index_rollback', os.path.join(app_dir, 'router', 'index.py')
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UploadFileRollbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_module = _load_index_module()

    def test_uploadFile_rolls_back_save_on_insert_error(self):
        """upload_file 在 insert_into_index 失败时应删除已保存的永久文件"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            load_dir = os.path.join(tmp_dir, 'load')
            save_dir = os.path.join(tmp_dir, 'save')
            os.makedirs(load_dir)
            os.makedirs(save_dir)

            with patch.object(self.index_module, 'LOAD_PATH', load_dir), \
                 patch.object(self.index_module, 'SAVE_PATH', save_dir), \
                 patch.object(
                    self.index_module, 'insert_into_index',
                    new_callable=AsyncMock,
                    side_effect=Exception("simulated ingest failure"),
                 ):
                app = FastAPI()
                app.include_router(self.index_module.index_app, prefix='/index')
                fake_index = type('FakeIndex', (), {'index_id': 'demo'})()
                app.dependency_overrides[self.index_module.get_index] = lambda: fake_index
                client = TestClient(app)

                response = client.post(
                    '/index/demo/uploadFile',
                    files={'file': ('note.txt', b'hello world', 'text/plain')},
                )

                self.assertEqual(response.status_code, 400)
                # 永久文件应被回滚删除
                saved_file = os.path.join(save_dir, 'demo', 'note.txt')
                self.assertFalse(
                    os.path.exists(saved_file),
                    "永久文件应在 insert_into_index 失败时被回滚删除",
                )
                # 临时文件也应被清理
                temp_files = os.listdir(load_dir)
                self.assertEqual(len(temp_files), 0, "临时文件应被清理")

    def test_uploadFiles_rolls_back_all_saved_on_error(self):
        """upload_files 在批量插入失败时应删除所有已保存的永久文件"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            load_dir = os.path.join(tmp_dir, 'load')
            save_dir = os.path.join(tmp_dir, 'save')
            os.makedirs(load_dir)
            os.makedirs(save_dir)

            with patch.object(self.index_module, 'LOAD_PATH', load_dir), \
                 patch.object(self.index_module, 'SAVE_PATH', save_dir), \
                 patch.object(
                    self.index_module, 'insert_into_index',
                    new_callable=AsyncMock,
                    side_effect=Exception("simulated ingest failure"),
                 ):
                app = FastAPI()
                app.include_router(self.index_module.index_app, prefix='/index')
                fake_index = type('FakeIndex', (), {'index_id': 'demo'})()
                app.dependency_overrides[self.index_module.get_index] = lambda: fake_index
                client = TestClient(app)

                response = client.post(
                    '/index/demo/uploadFiles',
                    files=[
                        ('files', ('file1.txt', b'content1', 'text/plain')),
                        ('files', ('file2.txt', b'content2', 'text/plain')),
                    ],
                )

                self.assertEqual(response.status_code, 400)
                # 两个永久文件都应被回滚删除
                for fname in ['file1.txt', 'file2.txt']:
                    saved_file = os.path.join(save_dir, 'demo', fname)
                    self.assertFalse(
                        os.path.exists(saved_file),
                        f"{fname} 应在批量插入失败时被回滚删除",
                    )

    def test_uploadFile_rejects_invalid_file_type(self):
        """upload_file 应拒绝不在允许列表中的文件类型"""
        with patch.object(self.index_module, 'LOAD_PATH', '/tmp'), \
             patch.object(self.index_module, 'SAVE_PATH', '/tmp'):
            app = FastAPI()
            app.include_router(self.index_module.index_app, prefix='/index')
            fake_index = type('FakeIndex', (), {'index_id': 'demo'})()
            app.dependency_overrides[self.index_module.get_index] = lambda: fake_index
            client = TestClient(app)

            response = client.post(
                '/index/demo/uploadFile',
                files={'file': ('malware.exe', b'binary', 'application/octet-stream')},
            )

            self.assertEqual(response.status_code, 400)

    def test_uploadFile_saves_to_index_specific_subdirectory(self):
        """upload_file 应将文件保存到按 index_id 分子目录的路径"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            load_dir = os.path.join(tmp_dir, 'load')
            save_dir = os.path.join(tmp_dir, 'save')
            os.makedirs(load_dir)
            os.makedirs(save_dir)

            with patch.object(self.index_module, 'LOAD_PATH', load_dir), \
                 patch.object(self.index_module, 'SAVE_PATH', save_dir), \
                 patch.object(
                    self.index_module, 'insert_into_index',
                    new_callable=AsyncMock,
                 ):
                app = FastAPI()
                app.include_router(self.index_module.index_app, prefix='/index')
                fake_index = type('FakeIndex', (), {'index_id': 'my-kb'})()
                app.dependency_overrides[self.index_module.get_index] = lambda: fake_index
                client = TestClient(app)

                response = client.post(
                    '/index/my-kb/uploadFile',
                    files={'file': ('data.txt', b'test data', 'text/plain')},
                )

                self.assertEqual(response.status_code, 200)
                saved_file = os.path.join(save_dir, 'my-kb', 'data.txt')
                self.assertTrue(os.path.exists(saved_file))
                with open(saved_file, 'rb') as f:
                    self.assertEqual(f.read(), b'test data')


if __name__ == '__main__':
    unittest.main()
