import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from main import app
from router.index import get_index

import tests._pathsetup  # noqa: F401


class MainWorkflowHttpTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = MagicMock()
        self.fake_index.index_id = "test_index"
        self.fake_index.summary = "This is a test summary"

        # Override dependency
        app.dependency_overrides[get_index] = lambda: self.fake_index
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch('router.index.list_index_names')
    @patch('router.index.createIndex')
    @patch('router.index.loadAllIndexes')
    def test_create_index_workflow(self, mock_load, mock_create, mock_list):
        mock_list.return_value = []
        response = self.client.post("/index/create", data={"index_name": "New Index"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "success",
            "msg": "index New_Index created",
            "index_name": "New_Index"
        })
        mock_create.assert_called_once_with("New_Index")

    @patch('router.index.insert_into_index')
    def test_upload_file_workflow(self, mock_insert):
        response = self.client.post(
            "/index/test_index/uploadFile",
            files={"file": ("test.txt", b"hello test contents", "text/plain")}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "inserted"})
        mock_insert.assert_called_once()

    @patch('router.index.saveIndex')
    def test_insert_doc_workflow(self, mock_save):
        response = self.client.post(
            "/index/test_index/insertdoc",
            data={"text": "hello doc text", "doc_id": "doc123"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        mock_save.assert_called_once_with(self.fake_index)

    @patch('handlers.qa_workflow.QAWorkflow')
    def test_query_workflow(self, mock_workflow_cls):
        from handlers.qa_workflow import QAWorkflowResult

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(
            return_value=QAWorkflowResult(response="answer text", source_nodes=[])
        )
        mock_workflow_cls.return_value = mock_instance

        response = self.client.post("/graph/query", data={"query": "what is this?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "answer text"})

    @patch('router.index.list_index_names')
    @patch('router.index.delete_collection')
    @patch('router.index.loadAllIndexes')
    def test_delete_index_workflow(self, mock_load, mock_delete, mock_list):
        mock_list.return_value = ["test_index"]
        response = self.client.post("/index/delete", data={"index_name": "test_index"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "deleted"})
        mock_delete.assert_called_once_with("test_index")

if __name__ == '__main__':
    unittest.main()
