import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from main import app
from router.index import get_index

import tests._pathsetup  # noqa: F401


@patch('router.index.list_index_names')
@patch('router.index.createIndex')
@patch('router.index.loadAllIndexes')
@patch('router.index.delete_collection')
@patch('router.index.insert_into_index')
@patch('router.index.get_all_docs')
@patch('router.index.updateNodeById')
@patch('router.index.deleteNodeById')
@patch('router.index.deleteDocById')
@patch('router.index.saveIndex')
@patch('router.index.summary_index')
class TestIndexRouter(unittest.TestCase):

    def setUp(self):
        self.fake_index = MagicMock()
        self.fake_index.index_id = "test_index"
        self.fake_index.summary = "test summary"

        app.dependency_overrides[get_index] = lambda: self.fake_index
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    # --- GET /index/ ---
    def test_root(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        response = self.client.get("/index/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "load": "ok"})

    # --- GET /index/list ---
    def test_list_indexes(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        idx1 = MagicMock()
        idx1.index_id = "alpha"
        idx2 = MagicMock()
        idx2.index_id = "beta"
        from router.index import indexes
        indexes.clear()
        indexes.extend([idx1, idx2])

        response = self.client.get("/index/list")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"indexes": ["alpha", "beta"]})

    # --- POST /index/create ---
    def test_create_index_success(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_list_index_names.return_value = []

        response = self.client.post("/index/create", data={"index_name": "New Index"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "success",
            "msg": "index New_Index created",
            "index_name": "New_Index"
        })
        mock_createIndex.assert_called_once_with("New_Index")
        mock_loadAllIndexes.assert_called_once()

    def test_create_index_duplicate(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_list_index_names.return_value = ["existing_index"]

        response = self.client.post("/index/create", data={"index_name": "existing_index"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "error", "msg": "index already exists"})
        mock_createIndex.assert_not_called()

    # --- POST /index/delete ---
    def test_delete_index_success(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_list_index_names.return_value = ["test_index"]

        response = self.client.post("/index/delete", data={"index_name": "test_index"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "deleted"})
        mock_delete_collection.assert_called_once_with("test_index")
        mock_loadAllIndexes.assert_called_once()

    def test_delete_index_not_found(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_list_index_names.return_value = ["existing_index"]

        response = self.client.post("/index/delete", data={"index_name": "nonexistent"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"status": "detail", "message": "index not exist"})
        mock_delete_collection.assert_not_called()

    # --- GET /index/{name}/info ---
    def test_index_info(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_get_all_docs.return_value = [{"doc_id": "doc1"}, {"doc_id": "doc2"}]

        response = self.client.get("/index/test_index/info")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"docs": [{"doc_id": "doc1"}, {"doc_id": "doc2"}]})

    # --- POST /index/{name}/query ---
    def test_query_index(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        class FakeResponse:
            def __init__(self, text):
                self.response = text
            def __str__(self):
                return self.response

        mock_engine = MagicMock()
        async def mock_aquery(q):
            return FakeResponse("query answer")
        mock_engine.aquery = mock_aquery

        with patch('router.index.Prompts') as mock_prompts, \
             patch('router.index.RetrieverQueryEngine') as mock_retriever_query_engine:
            mock_prompts.QA_PROMPT.value.template = "QA template"
            mock_prompts.REFINE_PROMPT.value.template = "Refine template"
            mock_retriever_query_engine.from_args.return_value = mock_engine
            response = self.client.post("/index/test_index/query", data={"query": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "query answer"})

    # --- POST /index/{name}/update ---
    def test_update_node_success(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_updateNodeById.return_value = None

        response = self.client.post(
            "/index/test_index/update?nodeId=node123",
            data={"text": "updated text"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "updated"})
        mock_updateNodeById.assert_called_once_with(self.fake_index, "node123", "updated text")

    def test_update_node_not_found(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_updateNodeById.side_effect = ValueError("not found")

        response = self.client.post(
            "/index/test_index/update?nodeId=bad_id",
            data={"text": "text"}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"status": "detail", "message": "node_id not exist"})

    # --- POST /index/{name}/uploadFile ---
    @patch('router.index.validate_upload_file')
    @patch('router.index.safe_filename')
    @patch('router.index.uuid.uuid4')
    @patch('router.index.aiofiles.open')
    def test_upload_file_success(
        self,
        mock_aio, mock_uuid, mock_safe, mock_validate,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_safe.return_value = "test.txt"
        mock_uuid.return_value = "uuid123"
        mock_validate.return_value = None

        response = self.client.post(
            "/index/test_index/uploadFile",
            files={"file": ("test.txt", b"file content", "text/plain")}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "inserted"})
        mock_insert_into_index.assert_called_once()

    @patch('router.index.validate_upload_file')
    def test_upload_file_invalid(
        self,
        mock_validate,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        from utils.upload import InvalidFileTypeError
        mock_validate.side_effect = InvalidFileTypeError("bad type")

        response = self.client.post(
            "/index/test_index/uploadFile",
            files={"file": ("test.bad", b"data", "application/octet-stream")}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("bad type", response.text)

    # --- POST /index/{name}/uploadFiles ---
    @patch('router.index.validate_upload_file')
    @patch('router.index.safe_filename')
    @patch('router.index.uuid.uuid4')
    @patch('router.index.aiofiles.open')
    @patch('handlers.graph_builder.summary_index')
    @patch('handlers.index_crud._save_summary')
    def test_upload_files_success(
        self,
        mock_save_summary, mock_summary, mock_aio,
        mock_uuid, mock_safe, mock_validate,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_safe.side_effect = lambda x: x
        mock_uuid.return_value = "u1"
        mock_validate.return_value = None
        mock_summary.return_value = "generated summary"

        response = self.client.post(
            "/index/test_index/uploadFiles",
            files=[
                ("files", ("a.txt", b"aaa", "text/plain")),
                ("files", ("b.txt", b"bbb", "text/plain")),
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "inserted"})
        self.assertEqual(mock_insert_into_index.call_count, 2)
        mock_save_summary.assert_called_once()

    # --- POST /index/{name}/upload_file_by_QA ---
    @patch('router.index.read_file_contents')
    @patch('router.index.build_qa_generation_prompt')
    @patch('router.index.generate_qa_batched')
    @patch('router.index.formatted_pairs')
    @patch('router.index.extract_content_after_backslash')
    @patch('router.index.embeddingQA')
    def test_upload_qa(
        self,
        mock_embed, mock_extract, mock_formatted, mock_gen_qa,
        mock_build_prompt, mock_read,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_read.return_value = "file contents"
        mock_build_prompt.return_value = "safe prompt"
        mock_gen_qa.return_value = [{"q": "q1", "a": "a1"}]
        mock_formatted.return_value = "formatted"
        mock_extract.return_value = "doc_id_123"

        response = self.client.post(
            "/index/test_index/upload_file_by_QA",
            data={"prompt": "generate QA"},
            files={"file": ("notes.txt", b"some content", "text/plain")}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        mock_embed.assert_called_once_with(self.fake_index, "formatted", "doc_id_123")

    # --- POST /index/{name}/deleteDoc ---
    def test_delete_doc_success(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_get_all_docs.return_value = [{"doc_id": "doc1"}, {"doc_id": "doc2"}]
        mock_deleteDocById.return_value = None

        response = self.client.post("/index/test_index/deleteDoc?doc_id=doc1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "deleted"})
        mock_deleteDocById.assert_called_once_with(self.fake_index, "doc1")

    def test_delete_doc_not_found(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_get_all_docs.return_value = [{"doc_id": "doc1"}]

        response = self.client.post("/index/test_index/deleteDoc?doc_id=nonexistent")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"status": "detail", "message": "doc_id: not found"})

    def test_delete_doc_error(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_get_all_docs.return_value = [{"doc_id": "doc1"}]
        mock_deleteDocById.side_effect = Exception("db error")

        response = self.client.post("/index/test_index/deleteDoc?doc_id=doc1")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"status": "detail", "message": "删除文档时出错"})

    # --- POST /index/{name}/deleteNode ---
    def test_delete_node_success(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_deleteNodeById.return_value = None

        response = self.client.post("/index/test_index/deleteNode?node_id=n1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "deleted"})
        mock_deleteNodeById.assert_called_once_with(self.fake_index, "n1")

    def test_delete_node_not_found(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_deleteNodeById.side_effect = Exception("not found")

        response = self.client.post("/index/test_index/deleteNode?node_id=bad")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"status": "detail", "message": "node_id: not found"})

    # --- GET /index/{name}/get_summary ---
    def test_get_summary(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        response = self.client.get("/index/test_index/get_summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"summary": "test summary"})

    # --- POST /index/{name}/set_summary ---
    def test_set_summary(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        response = self.client.post(
            "/index/test_index/set_summary",
            data={"summary": "new summary"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "summary": "new summary"})
        self.assertEqual(self.fake_index.summary, "new summary")
        mock_saveIndex.assert_called_once_with(self.fake_index)

    # --- POST /index/{name}/generate_summary ---
    def test_generate_summary(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_summary_index.return_value = "generated summary"

        response = self.client.post("/index/test_index/generate_summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "summary": "generated summary"})
        self.assertEqual(self.fake_index.summary, "generated summary")
        mock_saveIndex.assert_called_once_with(self.fake_index)

    # --- POST /index/{name}/insertdoc ---
    def test_insert_doc_with_doc_id(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        response = self.client.post(
            "/index/test_index/insertdoc",
            data={"text": "hello world", "doc_id": "doc123"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.fake_index.insert_nodes.assert_called_once()
        mock_saveIndex.assert_called_once_with(self.fake_index)

    def test_insert_doc_without_doc_id(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        response = self.client.post(
            "/index/test_index/insertdoc",
            data={"text": "plain text"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    # --- POST /index/{name}/save ---
    def test_save_index(
        self,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        response = self.client.post("/index/test_index/save")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        mock_saveIndex.assert_called_once_with(self.fake_index)

    # --- POST /index/{name}/getfile ---
    @patch('router.index.citf')
    def test_get_file(
        self, mock_citf,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_citf.return_value = None

        response = self.client.post("/index/test_index/getfile")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        mock_citf.assert_called_once_with(self.fake_index, "test_index.txt")

    # --- POST /index/{name}/evaluator ---
    @patch('router.index.build_llm')
    @patch('llama_index.core.evaluation.ResponseEvaluator')
    def test_evaluator(
        self, mock_eval_cls, mock_build_llm,
        mock_summary_index, mock_saveIndex, mock_deleteDocById,
        mock_deleteNodeById, mock_updateNodeById, mock_get_all_docs,
        mock_insert_into_index, mock_delete_collection, mock_loadAllIndexes,
        mock_createIndex, mock_list_index_names,
    ):
        mock_llm = MagicMock()
        mock_build_llm.return_value = mock_llm

        mock_evaluator = MagicMock()
        mock_eval_cls.return_value = mock_evaluator
        async def mock_aevaluate(**kwargs):
            result = MagicMock()
            result.__str__ = lambda self: "evaluation result"
            return result
        mock_evaluator.aevaluate = mock_aevaluate

        mock_engine = MagicMock()
        async def mock_aquery(q):
            resp = MagicMock()
            resp.response = "query answer"
            return resp
        mock_engine.aquery = mock_aquery
        self.fake_index.as_query_engine.return_value = mock_engine

        response = self.client.post(
            "/index/test_index/evaluator",
            data={"query": "test query"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"result": "evaluation result"})


if __name__ == '__main__':
    unittest.main()
