import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

import handlers.llama_handler as lh
import configs.load_env as env_config
import handlers.index_crud as index_crud


class FakeIndex:
    def __init__(self, index_id='test-index'):
        self.index_id = index_id
        self.inserted_docs = []
        self.storage_context = MagicMock()
        self.docstore = MagicMock()

    def insert(self, doc):
        self.inserted_docs.append(doc)


class LoadAllIndexesTest(unittest.TestCase):
    def setUp(self):
        lh.indexes.clear()
        self._orig_get_folders_list = index_crud.get_folders_list
        self._orig_storage_context = index_crud.StorageContext
        self._orig_load_index = index_crud.load_index_from_storage

        index_crud.get_folders_list = MagicMock(return_value=['a', 'b'])
        index_crud.StorageContext = MagicMock()
        index_crud.StorageContext.from_defaults = MagicMock(return_value='fake-storage-context')
        index_crud.load_index_from_storage = MagicMock(side_effect=lambda ctx: FakeIndex())

    def tearDown(self):
        lh.indexes.clear()
        index_crud.get_folders_list = self._orig_get_folders_list
        index_crud.StorageContext = self._orig_storage_context
        index_crud.load_index_from_storage = self._orig_load_index

    def test_does_not_duplicate_on_repeated_calls(self):
        asyncio.run(lh.loadAllIndexes())
        self.assertEqual(len(lh.indexes), 2)

        asyncio.run(lh.loadAllIndexes())
        self.assertEqual(len(lh.indexes), 2, 'calling loadAllIndexes twice should not duplicate entries')


class EmbeddingQATest(unittest.TestCase):
    def test_two_calls_without_explicit_id_get_different_ids(self):
        index1 = FakeIndex()
        index2 = FakeIndex()

        lh.embeddingQA(index1, ['q1', 'a1'])
        lh.embeddingQA(index2, ['q2', 'a2'])

        id1 = index1.inserted_docs[0].id_
        id2 = index2.inserted_docs[0].id_
        self.assertNotEqual(id1, id2, 'each call without an explicit id must get a fresh uuid')


class SaveIndexTest(unittest.TestCase):
    def setUp(self):
        self._orig_dir = env_config.index_save_directory
        env_config.index_save_directory = 'data/indexes'  # no trailing slash
        # Also patch in index_crud since it imported the value at module load
        self._orig_crud_dir = index_crud.index_save_directory
        index_crud.index_save_directory = 'data/indexes'

    def tearDown(self):
        env_config.index_save_directory = self._orig_dir
        index_crud.index_save_directory = self._orig_crud_dir

    def test_uses_proper_path_join(self):
        index = FakeIndex(index_id='myindex')
        lh.saveIndex(index)
        index.storage_context.persist.assert_called_once_with(
            os.path.join('data/indexes', 'myindex')
        )


class UpdateNodeByIdTest(unittest.TestCase):
    def test_persists_after_update(self):
        node = MagicMock()
        index = FakeIndex(index_id='myindex')
        index.docstore.docs = {'n1': node}

        lh.updateNodeById(index, 'n1', 'new text')

        node.set_content.assert_called_once_with('new text')
        index.docstore.add_documents.assert_called_once_with([node])
        index.storage_context.persist.assert_called_once()


if __name__ == '__main__':
    unittest.main()
