import asyncio
import unittest
from unittest.mock import MagicMock

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)

import handlers.index_crud as lh
import handlers.index_crud as index_crud


class FakeIndex:
    def __init__(self, index_id='test-index'):
        self.index_id = index_id
        self.inserted_docs = []
        self.storage_context = MagicMock()
        self.docstore = MagicMock()
        self.summary = ''

    def insert_nodes(self, nodes):
        self.inserted_docs.extend(nodes)

    def set_index_id(self, name):
        self.index_id = name


class LoadAllIndexesTest(unittest.TestCase):
    def setUp(self):
        lh.indexes.clear()
        self._orig_list_index_names = index_crud.list_index_names
        self._orig_get_or_create_collection = index_crud.get_or_create_collection
        self._orig_build_index_from_collection = index_crud.build_index_from_collection

        index_crud.list_index_names = MagicMock(return_value=['a', 'b'])
        index_crud.get_or_create_collection = MagicMock(return_value=MagicMock())
        index_crud.build_index_from_collection = MagicMock(side_effect=lambda c: FakeIndex())

    def tearDown(self):
        lh.indexes.clear()
        index_crud.list_index_names = self._orig_list_index_names
        index_crud.get_or_create_collection = self._orig_get_or_create_collection
        index_crud.build_index_from_collection = self._orig_build_index_from_collection

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
        self._orig_get_or_create_collection = index_crud.get_or_create_collection
        self._fake_collection = MagicMock()
        index_crud.get_or_create_collection = MagicMock(return_value=self._fake_collection)

    def tearDown(self):
        index_crud.get_or_create_collection = self._orig_get_or_create_collection

    def test_saves_summary_to_collection_metadata(self):
        index = FakeIndex(index_id='myindex')
        index.summary = 'test summary'
        lh.saveIndex(index)
        self._fake_collection.modify.assert_called_once_with(
            metadata={"summary": 'test summary'}
        )


class UpdateNodeByIdTest(unittest.TestCase):
    def test_updates_node_content(self):
        node = MagicMock()
        index = FakeIndex(index_id='myindex')
        index.docstore.docs = {'n1': node}

        lh.updateNodeById(index, 'n1', 'new text')

        node.set_content.assert_called_once_with('new text')
        index.docstore.add_documents.assert_called_once_with([node])


if __name__ == '__main__':
    unittest.main()
