import builtins
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


def _load_index_module():
    app_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')
    spec = importlib.util.spec_from_file_location(
        'router_index_standalone',
        os.path.join(app_dir, 'router', 'index.py')
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UploadFileUsesAsyncIoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_module = _load_index_module()

    def test_uploadFile_does_not_use_blocking_open(self):
        """async def upload_file used plain with open(...) f.write(...), blocking the
        event loop -- the sibling uploadFiles (plural) endpoint already uses aiofiles
        for the same job. This must too."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            load_dir = os.path.join(tmp_dir, 'load')
            save_dir = os.path.join(tmp_dir, 'save')
            os.makedirs(load_dir)
            os.makedirs(save_dir)

            with patch.object(self.index_module, 'LOAD_PATH', load_dir), \
                 patch.object(self.index_module, 'SAVE_PATH', save_dir), \
                 patch.object(self.index_module, 'insert_into_index'):

                app = FastAPI()
                app.include_router(self.index_module.index_app, prefix='/index')
                fake_index = type('FakeIndex', (), {'index_id': 'demo'})()
                app.dependency_overrides[self.index_module.get_index] = lambda: fake_index
                client = TestClient(app)

                original_open = builtins.open

                def guarded_open(file, *args, **kwargs):
                    if isinstance(file, str) and (file.startswith(load_dir) or file.startswith(save_dir)):
                        raise AssertionError(f"blocking open() was used for {file!r}; expected aiofiles.open")
                    return original_open(file, *args, **kwargs)

                with patch.object(builtins, 'open', side_effect=guarded_open):
                    response = client.post(
                        '/index/demo/uploadFile',
                        files={'file': ('note.txt', b'hello world', 'text/plain')},
                    )

                self.assertEqual(response.status_code, 200)

    def test_uploadFile_still_delivers_correct_bytes_to_insert_into_index(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            load_dir = os.path.join(tmp_dir, 'load')
            save_dir = os.path.join(tmp_dir, 'save')
            os.makedirs(load_dir)
            os.makedirs(save_dir)

            with patch.object(self.index_module, 'LOAD_PATH', load_dir), \
                 patch.object(self.index_module, 'SAVE_PATH', save_dir), \
                 patch.object(self.index_module, 'insert_into_index') as mock_insert:

                app = FastAPI()
                app.include_router(self.index_module.index_app, prefix='/index')
                fake_index = type('FakeIndex', (), {'index_id': 'demo'})()
                app.dependency_overrides[self.index_module.get_index] = lambda: fake_index
                client = TestClient(app)

                response = client.post(
                    '/index/demo/uploadFile',
                    files={'file': ('note.txt', b'hello world', 'text/plain')},
                )

                self.assertEqual(response.status_code, 200)
                mock_insert.assert_called_once()
                with open(os.path.join(save_dir, 'note.txt'), 'rb') as f:
                    self.assertEqual(f.read(), b'hello world')


if __name__ == '__main__':
    unittest.main()
