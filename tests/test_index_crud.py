import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import handlers.index_crud as index_crud

import tests._pathsetup  # noqa: F401


class FakeIndex:
    def __init__(self, index_id="test-index"):
        self.index_id = index_id
        self.inserted_docs = []
        self.summary = ""
        self.vector_store = MagicMock()

    def insert_nodes(self, nodes):
        self.inserted_docs.extend(nodes)

    def set_index_id(self, name):
        self.index_id = name


class CreateIndexTest(unittest.TestCase):
    @patch("handlers.index_crud.create_empty_index")
    def test_creates_index_and_sets_id(self, mock_create_empty):
        fake_index = FakeIndex()
        mock_create_empty.return_value = fake_index

        index_crud.createIndex("my_index")

        self.assertEqual(fake_index.index_id, "my_index")
        mock_create_empty.assert_called_once_with("my_index")


class InsertIntoIndexTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="test_idx")
        self._orig_get_or_create_collection = index_crud.get_or_create_collection
        self._fake_collection = MagicMock()
        index_crud.get_or_create_collection = MagicMock(return_value=self._fake_collection)

    def tearDown(self):
        index_crud.get_or_create_collection = self._orig_get_or_create_collection

    @patch("handlers.vector_store.persist_docstore")
    @patch("handlers.vector_store.load_or_create_docstore")
    @patch("handlers.ingestion_pipeline.ingest_files")
    @patch("handlers.ingestion_pipeline.build_pipeline")
    @patch("handlers.graph_builder.summary_index")
    def test_ingests_file_via_pipeline_and_updates_summary(
        self, mock_summary, mock_build_pipeline, mock_ingest_files, mock_load_docstore, mock_persist_docstore
    ):
        mock_docstore = MagicMock()
        mock_load_docstore.return_value = mock_docstore
        mock_pipeline = MagicMock()
        mock_build_pipeline.return_value = mock_pipeline
        mock_summary.return_value = "generated summary"

        asyncio.run(index_crud.insert_into_index(self.fake_index, "/path/to/file.pdf"))

        mock_load_docstore.assert_called_once_with("test_idx")
        mock_build_pipeline.assert_called_once_with(
            vector_store=self.fake_index.vector_store, docstore=mock_docstore
        )
        mock_ingest_files.assert_called_once_with([Path("/path/to/file.pdf")], mock_pipeline)
        mock_persist_docstore.assert_called_once_with("test_idx", mock_docstore)
        self.assertEqual(self.fake_index.summary, "generated summary")
        mock_summary.assert_called_once_with(self.fake_index)

    @patch("handlers.vector_store.persist_docstore")
    @patch("handlers.vector_store.load_or_create_docstore")
    @patch("handlers.ingestion_pipeline.ingest_files")
    @patch("handlers.ingestion_pipeline.build_pipeline")
    @patch("handlers.graph_builder.summary_index")
    def test_skip_summary_does_not_regenerate_summary(
        self, mock_summary, mock_build_pipeline, mock_ingest_files, mock_load_docstore, mock_persist_docstore
    ):
        asyncio.run(index_crud.insert_into_index(self.fake_index, "/path/to/file.pdf", skip_summary=True))

        mock_ingest_files.assert_called_once()
        mock_summary.assert_not_called()
        self.assertEqual(self.fake_index.summary, "")


class GetAllDocsTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="test_idx")
        self._fake_collection = MagicMock()
        self._fake_client = MagicMock()
        self._fake_client.get_collection.return_value = self._fake_collection
        self._patcher = patch("handlers.index_crud._get_client", return_value=self._fake_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_returns_docs_when_chromadb_has_data(self):
        self._fake_collection.get.return_value = {
            "ids": ["n1", "n2"],
            "documents": ["text1", "text2"],
            "metadatas": [{"ref_doc_id": "doc_a"}, {"ref_doc_id": "doc_b"}],
        }

        result = index_crud.get_all_docs(self.fake_index)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["node_id"], "n1")
        self.assertEqual(result[0]["text"], "text1")
        self.assertEqual(result[0]["doc_id"], "doc_a")
        self.assertEqual(result[1]["node_id"], "n2")
        self.assertEqual(result[1]["text"], "text2")
        self.assertEqual(result[1]["doc_id"], "doc_b")

    def test_returns_empty_list_when_no_data(self):
        self._fake_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        result = index_crud.get_all_docs(self.fake_index)

        self.assertEqual(result, [])

    def test_returns_empty_list_when_chromadb_raises_exception(self):
        self._fake_collection.get.side_effect = Exception("chroma error")

        result = index_crud.get_all_docs(self.fake_index)

        self.assertEqual(result, [])


class UpdateNodeByIdTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="test_idx")
        self._fake_collection = MagicMock()
        self._fake_client = MagicMock()
        self._fake_client.get_collection.return_value = self._fake_collection
        self._patcher = patch("handlers.index_crud._get_client", return_value=self._fake_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_updates_node_text(self):
        self._fake_collection.get.return_value = {"ids": ["n1"], "documents": ["old"], "metadatas": [{}]}

        index_crud.updateNodeById(self.fake_index, "n1", "new text")

        self._fake_collection.update.assert_called_once_with(ids=["n1"], documents=["new text"])

    def test_raises_key_error_when_node_not_found(self):
        self._fake_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        with self.assertRaises(KeyError):
            index_crud.updateNodeById(self.fake_index, "missing", "text")


class DeleteNodeByIdTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="test_idx")
        self._fake_collection = MagicMock()
        self._fake_client = MagicMock()
        self._fake_client.get_collection.return_value = self._fake_collection
        self._patcher = patch("handlers.index_crud._get_client", return_value=self._fake_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_deletes_node(self):
        self._fake_collection.get.return_value = {"ids": ["n1"], "documents": ["text"], "metadatas": [{}]}

        index_crud.deleteNodeById(self.fake_index, "n1")

        self._fake_collection.delete.assert_called_once_with(ids=["n1"])

    def test_raises_key_error_when_node_not_found(self):
        self._fake_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        with self.assertRaises(KeyError):
            index_crud.deleteNodeById(self.fake_index, "missing")


class DeleteDocByIdTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="test_idx")
        self._fake_collection = MagicMock()
        self._fake_client = MagicMock()
        self._fake_client.get_collection.return_value = self._fake_collection
        self._patcher = patch("handlers.index_crud._get_client", return_value=self._fake_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_deletes_nodes_with_matching_ref_doc_id(self):
        self._fake_collection.get.return_value = {
            "ids": ["n1", "n3"],
            "documents": ["a", "c"],
            "metadatas": [{"ref_doc_id": "doc_x"}, {"ref_doc_id": "doc_x"}],
        }

        index_crud.deleteDocById(self.fake_index, "doc_x")

        self._fake_collection.delete.assert_called_once_with(ids=["n1", "n3"])


class GetIndexByNameTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="target")
        index_crud.indexes.clear()
        index_crud.indexes.append(FakeIndex(index_id="other"))
        index_crud.indexes.append(self.fake_index)

    def tearDown(self):
        index_crud.indexes.clear()

    def test_returns_index_when_found(self):
        result = index_crud.get_index_by_name("target")
        self.assertIs(result, self.fake_index)

    def test_returns_none_when_not_found(self):
        result = index_crud.get_index_by_name("nonexistent")
        self.assertIsNone(result)


class SaveIndexTest(unittest.TestCase):
    def setUp(self):
        self._orig_get_or_create_collection = index_crud.get_or_create_collection
        self._fake_collection = MagicMock()
        index_crud.get_or_create_collection = MagicMock(return_value=self._fake_collection)

    def tearDown(self):
        index_crud.get_or_create_collection = self._orig_get_or_create_collection

    def test_saves_summary_to_collection_metadata(self):
        index = FakeIndex(index_id="myindex")
        index.summary = "test summary"

        index_crud.saveIndex(index)

        self._fake_collection.modify.assert_called_once_with(metadata={"summary": "test summary"})


class SaveSummaryTest(unittest.TestCase):
    def setUp(self):
        self._orig_get_or_create_collection = index_crud.get_or_create_collection
        self._fake_collection = MagicMock()
        index_crud.get_or_create_collection = MagicMock(return_value=self._fake_collection)

    def tearDown(self):
        index_crud.get_or_create_collection = self._orig_get_or_create_collection

    def test_saves_summary_directly(self):
        index = FakeIndex(index_id="summary_test")
        index.summary = "direct summary"

        index_crud._save_summary(index)

        self._fake_collection.modify.assert_called_once_with(metadata={"summary": "direct summary"})

    def test_saves_empty_summary_when_not_set(self):
        index = FakeIndex(index_id="no_summary")
        del index.summary

        index_crud._save_summary(index)

        self._fake_collection.modify.assert_called_once_with(metadata={"summary": ""})


class ConvertIndexToFileTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="convert_test")
        self.fake_node = MagicMock()
        self.fake_node.text = "node text content"
        self.fake_node.get_content = MagicMock(return_value="node text content")
        self.fake_index.docstore = MagicMock()
        self.fake_index.docstore.docs = {"node1": self.fake_node}

    @patch("aiofiles.open")
    @patch("handlers.index_crud.get_index_by_name")
    @patch("handlers.index_crud.os.makedirs")
    @patch("handlers.index_crud.os.path.exists", return_value=True)
    async def test_convert_index_to_file_writes_content(
        self, mock_exists, mock_makedirs, mock_get_index, mock_aiofiles_open
    ):
        mock_get_index.return_value = self.fake_index
        mock_file = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_aiofiles_open.return_value = mock_cm

        await index_crud.convert_index_to_file("convert_test", "output.txt")

        mock_get_index.assert_called_once_with("convert_test")
        mock_aiofiles_open.assert_called_once()
        mock_file.write.assert_called_once_with("node text content")

    @patch("aiofiles.open")
    @patch("handlers.index_crud.get_index_by_name")
    @patch("handlers.index_crud.os.makedirs")
    @patch("handlers.index_crud.os.path.exists", return_value=True)
    async def test_convert_index_to_file_skips_when_index_not_found(
        self, mock_exists, mock_makedirs, mock_get_index, mock_aiofiles_open
    ):
        mock_get_index.return_value = None

        await index_crud.convert_index_to_file("nonexistent", "output.txt")

        mock_aiofiles_open.assert_not_called()


class CitfTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="citf_test")
        self.fake_node = MagicMock()
        self.fake_node.text = "citf node text"
        self.fake_node.get_content = MagicMock(return_value="citf node text")
        self.fake_index.docstore = MagicMock()
        self.fake_index.docstore.docs = {"n1": self.fake_node}

    @patch("aiofiles.open")
    @patch("handlers.index_crud.os.makedirs")
    @patch("handlers.index_crud.os.path.exists", return_value=True)
    async def test_citf_writes_content(self, mock_exists, mock_makedirs, mock_aiofiles_open):
        mock_file = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_aiofiles_open.return_value = mock_cm

        await index_crud.citf(self.fake_index, "citf_output.txt")

        mock_aiofiles_open.assert_called_once()
        mock_file.write.assert_called_once_with("citf node text")

    @patch("aiofiles.open")
    @patch("handlers.index_crud.os.makedirs")
    @patch("handlers.index_crud.os.path.exists", return_value=False)
    async def test_citf_creates_directory_when_missing(
        self, mock_exists, mock_makedirs, mock_aiofiles_open
    ):
        mock_file = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_aiofiles_open.return_value = mock_cm

        await index_crud.citf(self.fake_index, "citf_output.txt")

        mock_makedirs.assert_called_once()


class GetDocsFromIndexTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="get_docs_test")
        self.fake_index.docstore = MagicMock()

    def test_returns_nodes_when_ref_doc_found(self):
        fake_ref_doc = MagicMock()
        fake_ref_doc.node_ids = ["node1", "node2"]
        self.fake_index.docstore.get_ref_doc_info.return_value = fake_ref_doc
        fake_nodes = [MagicMock(), MagicMock()]
        self.fake_index.docstore.get_nodes.return_value = fake_nodes

        result = index_crud.get_docs_from_index(self.fake_index, "doc_123")

        self.assertEqual(result, fake_nodes)
        self.fake_index.docstore.get_ref_doc_info.assert_called_once_with("doc_123")
        self.fake_index.docstore.get_nodes.assert_called_once_with(["node1", "node2"])

    def test_returns_empty_list_when_ref_doc_not_found(self):
        self.fake_index.docstore.get_ref_doc_info.return_value = None

        result = index_crud.get_docs_from_index(self.fake_index, "nonexistent")

        self.assertEqual(result, [])
        self.fake_index.docstore.get_nodes.assert_not_called()


class DeleteIndexTest(unittest.TestCase):
    @patch("handlers.index_crud.delete_collection")
    def test_delete_index_calls_delete_collection(self, mock_delete_collection):
        index_crud.delete_index("test_index_name")

        mock_delete_collection.assert_called_once_with("test_index_name")


class FormatSourceNodesListTest(unittest.TestCase):
    def test_formats_single_node(self):
        node = MagicMock()
        node.id_ = "node_1"
        node.text = "hello world"
        node_with_score = MagicMock()
        node_with_score.node = node

        result = index_crud.format_source_nodes_list([node_with_score])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "node_1")
        self.assertEqual(result[0]["text"], "hello world")

    def test_formats_multiple_nodes(self):
        nodes_data = []
        for i in range(3):
            node = MagicMock()
            node.id_ = f"node_{i}"
            node.text = f"text_{i}"
            nws = MagicMock()
            nws.node = node
            nodes_data.append(nws)

        result = index_crud.format_source_nodes_list(nodes_data)

        self.assertEqual(len(result), 3)
        for i in range(3):
            self.assertEqual(result[i]["id"], f"node_{i}")
            self.assertEqual(result[i]["text"], f"text_{i}")

    def test_returns_empty_list_for_empty_input(self):
        result = index_crud.format_source_nodes_list([])
        self.assertEqual(result, [])


class EmbeddingQATest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="qa_test")
        self._orig_get_or_create_collection = index_crud.get_or_create_collection
        self._fake_collection = MagicMock()
        index_crud.get_or_create_collection = MagicMock(return_value=self._fake_collection)

    def tearDown(self):
        index_crud.get_or_create_collection = self._orig_get_or_create_collection

    async def test_embeds_qa_pairs_and_inserts(self):
        qa_pairs = ["question1", "answer1", "question2", "answer2"]

        await index_crud.embeddingQA(self.fake_index, qa_pairs, id="test_id")

        self.assertEqual(len(self.fake_index.inserted_docs), 2)
        self.assertEqual(self.fake_index.inserted_docs[0].id_, "test_id_0")
        self.assertIn("question1", self.fake_index.inserted_docs[0].text)
        self.assertIn("answer1", self.fake_index.inserted_docs[0].text)
        self.assertEqual(self.fake_index.inserted_docs[1].id_, "test_id_1")
        self.assertIn("question2", self.fake_index.inserted_docs[1].text)
        self.assertIn("answer2", self.fake_index.inserted_docs[1].text)

    async def test_embeds_qa_without_id_generates_uuid(self):
        qa_pairs = ["q1", "a1"]

        await index_crud.embeddingQA(self.fake_index, qa_pairs)

        self.assertEqual(len(self.fake_index.inserted_docs), 1)
        self.assertIsNotNone(self.fake_index.inserted_docs[0].id_)

    async def test_embeds_handles_odd_number_of_qa_pairs(self):
        qa_pairs = ["q1", "a1", "orphan"]

        await index_crud.embeddingQA(self.fake_index, qa_pairs, id="odd")

        self.assertEqual(len(self.fake_index.inserted_docs), 1)
        self.assertEqual(self.fake_index.inserted_docs[0].id_, "odd_0")


class GetIndexByNameAsyncTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_index = FakeIndex(index_id="async_target")
        index_crud.indexes.clear()
        index_crud.indexes.append(FakeIndex(index_id="other"))
        index_crud.indexes.append(self.fake_index)

    def tearDown(self):
        index_crud.indexes.clear()

    async def test_returns_index_when_found(self):
        result = await index_crud.get_index_by_name_async("async_target")
        self.assertIs(result, self.fake_index)

    async def test_returns_none_when_not_found(self):
        result = await index_crud.get_index_by_name_async("nonexistent")
        self.assertIsNone(result)


class LoadAllIndexesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        index_crud.indexes.clear()
        self._patcher_list = patch("handlers.index_crud.list_index_names", return_value=["idx_a", "idx_b"])
        self._patcher_list.start()
        self._patcher_or_create = patch("handlers.index_crud.get_or_create_collection")
        self._mock_get_or_create = self._patcher_or_create.start()
        self._patcher_build = patch("handlers.index_crud.build_index_from_collection")
        self._mock_build = self._patcher_build.start()
        self._patcher_init = patch("configs.llm_predictor.init_settings")
        self._patcher_init.start()

        self.fake_collection = MagicMock()
        self.fake_collection.metadata = {"summary": "test summary"}
        self._mock_get_or_create.return_value = self.fake_collection

    def tearDown(self):
        self._patcher_list.stop()
        self._patcher_or_create.stop()
        self._patcher_build.stop()
        self._patcher_init.stop()
        index_crud.indexes.clear()

    async def test_loads_all_indexes(self):
        fake_index_a = FakeIndex(index_id="idx_a")
        fake_index_b = FakeIndex(index_id="idx_b")
        self._mock_build.side_effect = [fake_index_a, fake_index_b]

        await index_crud.loadAllIndexes()

        self.assertEqual(len(index_crud.indexes), 2)
        self.assertEqual(index_crud.indexes[0].index_id, "idx_a")
        self.assertEqual(index_crud.indexes[0].summary, "test summary")
        self.assertEqual(index_crud.indexes[1].index_id, "idx_b")
        self.assertEqual(index_crud.indexes[1].summary, "test summary")

    async def test_load_handles_exception_gracefully(self):
        fake_index_a = FakeIndex(index_id="idx_a")
        self._mock_build.side_effect = [fake_index_a, Exception("build failed")]

        await index_crud.loadAllIndexes()

        self.assertEqual(len(index_crud.indexes), 1)
        self.assertEqual(index_crud.indexes[0].index_id, "idx_a")


if __name__ == "__main__":
    unittest.main()
