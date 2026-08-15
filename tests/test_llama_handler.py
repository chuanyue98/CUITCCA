import asyncio
import unittest
from unittest.mock import MagicMock, patch

import handlers.index_crud as index_crud
import handlers.index_crud as lh

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


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
    """embeddingQA 现在走 IngestionPipeline（见 handlers/index_crud.py:
    _embed_qa_and_persist 的 docstring），doc_id 由内容 hash 决定，不再是
    随机 uuid——两个内容不同的问答对应该拿到不同的（确定性）doc_id，两次
    导入同一个问答对应该拿到相同的 doc_id（去重生效的前提）。mock 掉
    build_pipeline/load_or_create_docstore/persist_docstore，只验证
    embeddingQA 自己传给 pipeline 的 doc_id 是什么；真实的 UPSERTS 去重端到
    端行为见 tests/test_index_crud.py 的 EmbeddingQADedupTest（用真实
    pipeline + MockEmbedding）。"""

    @patch("handlers.vector_store.persist_docstore")
    @patch("handlers.vector_store.load_or_create_docstore")
    @patch("handlers.ingestion_pipeline.build_pipeline")
    def test_different_content_gets_different_content_hash_ids(
        self, mock_build_pipeline, mock_load_docstore, mock_persist_docstore
    ):
        mock_pipeline = MagicMock()
        mock_build_pipeline.return_value = mock_pipeline
        index1 = FakeIndex()
        index2 = FakeIndex()
        index1.vector_store = MagicMock()
        index2.vector_store = MagicMock()

        # embeddingQA is async
        asyncio.run(lh.embeddingQA(index1, ['q1', 'a1']))
        id1 = mock_pipeline.run.call_args.kwargs["documents"][0].id_

        asyncio.run(lh.embeddingQA(index2, ['q2', 'a2']))
        id2 = mock_pipeline.run.call_args.kwargs["documents"][0].id_

        self.assertNotEqual(id1, id2, 'different QA content must get different (content-hash) doc ids')


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
    def setUp(self):
        self._fake_collection = MagicMock()
        self._fake_collection.get.return_value = {'ids': ['n1'], 'documents': ['old text'], 'metadatas': [{}]}
        self._fake_client = MagicMock()
        self._fake_client.get_collection.return_value = self._fake_collection
        self._patcher = patch('handlers.index_crud._get_client', return_value=self._fake_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    @patch('llama_index.core.Settings')
    def test_updates_node_content(self, mock_settings):
        index = FakeIndex(index_id='myindex')
        mock_settings.embed_model.get_text_embedding.return_value = [0.1, 0.2, 0.3]
        lh.updateNodeById(index, 'n1', 'new text')
        self._fake_collection.update.assert_called_once_with(
            ids=['n1'], documents=['new text'], embeddings=[[0.1, 0.2, 0.3]]
        )


if __name__ == '__main__':
    unittest.main()
