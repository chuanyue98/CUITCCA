import unittest
from unittest.mock import MagicMock, patch

import tests._pathsetup  # noqa: F401


class VectorStoreTest(unittest.TestCase):

    def setUp(self):
        self._client_instance_patcher = patch('handlers.vector_store._client_instance', None)
        self._client_instance_patcher.start()
        self.mock_chroma_client = MagicMock()
        self.mock_chromadb_patch = patch('handlers.vector_store.chromadb.PersistentClient', return_value=self.mock_chroma_client)
        self.mock_chromadb = self.mock_chromadb_patch.start()

    def tearDown(self):
        self.mock_chromadb_patch.stop()
        self._client_instance_patcher.stop()
        from handlers.vector_store import _client_instance
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
        self.mock_chroma_client.get_or_create_collection.assert_called_once_with('test-col')
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
        from handlers.vector_store import delete_collection
        delete_collection('to-delete')
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

        self.mock_chroma_client.get_or_create_collection.assert_called_once_with('new-index')
        mock_cvs.assert_called_once_with(chroma_collection=fake_collection)
        mock_vsi.from_vector_store.assert_called_once_with(
            vector_store=fake_vector_store,
            embed_model=mock_settings.embed_model,
        )
        fake_index.set_index_id.assert_called_once_with('new-index')
        self.assertIs(result, fake_index)


if __name__ == '__main__':
    unittest.main()