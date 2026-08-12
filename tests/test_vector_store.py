import unittest
from unittest.mock import MagicMock, patch

import tests._pathsetup  # noqa: F401


class VectorStoreTest(unittest.TestCase):

    def setUp(self):
        self._client_instance_patcher = patch('handlers.vector_store._client_instance', None)
        self._client_instance_patcher.start()
        self.mock_chroma_client = MagicMock()
        self.mock_chromadb_patch = patch(
            'handlers.vector_store.chromadb.PersistentClient',
            return_value=self.mock_chroma_client,
        )
        self.mock_chromadb = self.mock_chromadb_patch.start()

    def tearDown(self):
        self.mock_chromadb_patch.stop()
        self._client_instance_patcher.stop()
        import handlers.vector_store as vs
        vs._client_instance = None

    def test_get_client_singleton(self):
        from handlers.vector_store import _get_client
        client1 = _get_client()
        client2 = _get_client()
        self.assertIs(client1, client2)
        self.mock_chromadb.assert_called_once()

    def test_get_or_create_collection_returns_collection(self):
        from handlers.vector_store import get_or_create_collection
        fake_collection = MagicMock()
        self.mock_chroma_client.get_or_create_collection.return_value = fake_collection
        result = get_or_create_collection('test-col')
        self.mock_chroma_client.get_or_create_collection.assert_called_once_with('test-col', metadata=None)
        self.assertIs(result, fake_collection)

    def test_list_index_names(self):
        from handlers.vector_store import list_index_names
        col1 = MagicMock()
        col1.name = 'idx-a'
        col2 = MagicMock()
        col2.name = 'idx-b'
        self.mock_chroma_client.list_collections.return_value = [col1, col2]
        names = list_index_names()
        self.assertEqual(names, ['idx-a', 'idx-b'])

    def test_delete_collection(self):
        # 注意：delete_collection 现在会顺带删除 {name}_docstore.json（见
        # test_delete_collection_removes_persisted_docstore），这里把
        # _docstore_persist_path 打掉，避免测试触碰真实的 index_save_directory
        from handlers.vector_store import delete_collection
        with patch('handlers.vector_store._docstore_persist_path', return_value='/tmp/never-exists_docstore.json'):
            delete_collection('to-delete')
        self.mock_chroma_client.delete_collection.assert_called_once_with('to-delete')

    def test_delete_collection_removes_persisted_docstore(self):
        # 回归：删除索引必须连带清理 {name}_docstore.json。不清理的话，重建
        # 同名索引后上传相同内容会被残留 docstore 的 UPSERTS 判重静默跳过
        # （实测可复现：接口返回 inserted 但 0 节点入库）。
        import os
        import tempfile

        from handlers.vector_store import delete_collection

        with tempfile.TemporaryDirectory() as tmpdir:
            docstore_path = os.path.join(tmpdir, 'to-delete_docstore.json')
            with open(docstore_path, 'w') as f:
                f.write('{}')
            with patch('handlers.vector_store._docstore_persist_path', return_value=docstore_path):
                delete_collection('to-delete')
            self.assertFalse(os.path.exists(docstore_path))
        self.mock_chroma_client.delete_collection.assert_called_once_with('to-delete')

    def test_delete_collection_tolerates_missing_docstore(self):
        # 从未摄取过的索引（无 docstore 文件）删除时也必须成功、不抛异常
        import os
        import tempfile

        from handlers.vector_store import delete_collection

        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = os.path.join(tmpdir, 'fresh-index_docstore.json')
            with patch('handlers.vector_store._docstore_persist_path', return_value=missing_path):
                delete_collection('fresh-index')
        self.mock_chroma_client.delete_collection.assert_called_once_with('fresh-index')

    def test_delete_collection_removes_saved_source_files(self):
        # 回归：删除索引必须连带清理 SAVE_PATH/{name}/ 下上传的源文件副本
        # （router/index.py uploadFiles 按 index.index_id 落盘）。不删的话磁盘
        # 留孤儿文件，重建同名索引后目录里还躺着旧源文件，容易让人误认归属。
        import os
        import tempfile

        from handlers.vector_store import delete_collection

        with tempfile.TemporaryDirectory() as tmpdir:
            save_root = os.path.join(tmpdir, 'upload_files')
            source_dir = os.path.join(save_root, 'to-delete')
            os.makedirs(source_dir)
            with open(os.path.join(source_dir, 'rules.txt'), 'w') as f:
                f.write('source')
            with patch('handlers.vector_store._docstore_persist_path',
                       return_value=os.path.join(tmpdir, 'never_docstore.json')), \
                 patch('handlers.vector_store.load_env.SAVE_PATH', save_root):
                delete_collection('to-delete')
            self.assertFalse(os.path.exists(source_dir))
        self.mock_chroma_client.delete_collection.assert_called_once_with('to-delete')

    def test_delete_collection_tolerates_missing_source_dir(self):
        # 从未上传过文件的索引（SAVE_PATH/{name}/ 不存在）删除时也必须成功
        import os
        import tempfile

        from handlers.vector_store import delete_collection

        with tempfile.TemporaryDirectory() as tmpdir:
            save_root = os.path.join(tmpdir, 'upload_files')
            with patch('handlers.vector_store._docstore_persist_path',
                       return_value=os.path.join(tmpdir, 'never_docstore.json')), \
                 patch('handlers.vector_store.load_env.SAVE_PATH', save_root):
                delete_collection('fresh-index')
        self.mock_chroma_client.delete_collection.assert_called_once_with('fresh-index')

    def test_delete_collection_does_not_touch_fs_when_save_path_empty(self):
        # 回归：模块级默认 SAVE_PATH 是空串（reload_env_variables 才填值），
        # 空串下 os.path.join('', name) 会返回裸 name——如果没守卫，rmtree
        # 会去删 CWD 下的同名目录。删除必须在 SAVE_PATH 为空时完全不碰文件系统。
        from handlers.vector_store import delete_collection

        with patch('handlers.vector_store._docstore_persist_path',
                   return_value='/tmp/never_docstore.json'), \
             patch('handlers.vector_store.load_env.SAVE_PATH', ''), \
             patch('handlers.vector_store.shutil.rmtree') as mock_rmtree:
            delete_collection('to-delete')
        mock_rmtree.assert_not_called()
        self.mock_chroma_client.delete_collection.assert_called_once_with('to-delete')

    @patch('handlers.vector_store.ChromaVectorStore')
    @patch('handlers.vector_store.VectorStoreIndex')
    @patch('handlers.vector_store.Settings')
    def test_build_index_from_collection(self, mock_settings, mock_vsi, mock_cvs):
        from handlers.vector_store import build_index_from_collection
        fake_collection = MagicMock()
        fake_vector_store = MagicMock()
        mock_cvs.return_value = fake_vector_store
        fake_index = MagicMock()
        mock_vsi.from_vector_store.return_value = fake_index

        result = build_index_from_collection(fake_collection)

        mock_cvs.assert_called_once_with(chroma_collection=fake_collection)
        mock_vsi.from_vector_store.assert_called_once_with(
            vector_store=fake_vector_store,
            embed_model=mock_settings.embed_model,
        )
        self.assertIs(result, fake_index)

    @patch('handlers.vector_store.ChromaVectorStore')
    @patch('handlers.vector_store.VectorStoreIndex')
    @patch('handlers.vector_store.Settings')
    def test_create_empty_index(self, mock_settings, mock_vsi, mock_cvs):
        from handlers.vector_store import create_empty_index
        fake_collection = MagicMock()
        self.mock_chroma_client.get_or_create_collection.return_value = fake_collection
        fake_vector_store = MagicMock()
        mock_cvs.return_value = fake_vector_store
        fake_index = MagicMock()
        mock_vsi.from_vector_store.return_value = fake_index

        result = create_empty_index('new-index')

        self.mock_chroma_client.get_or_create_collection.assert_called_once_with('new-index', metadata=None)
        mock_cvs.assert_called_once_with(chroma_collection=fake_collection)
        mock_vsi.from_vector_store.assert_called_once_with(
            vector_store=fake_vector_store,
            embed_model=mock_settings.embed_model,
        )
        fake_index.set_index_id.assert_called_once_with('new-index')
        self.assertIs(result, fake_index)


if __name__ == '__main__':
    unittest.main()
