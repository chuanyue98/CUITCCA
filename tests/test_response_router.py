import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from main import app
from dependencies.index_dep import get_index

import tests._pathsetup  # noqa: F401


class ResponseRouterTest(unittest.TestCase):
    def setUp(self):
        self.fake_index = MagicMock()
        self.fake_engine = MagicMock()

        class FakeResponse:
            response = "mock answer"
            def __str__(self):
                return self.response

        async def mock_aquery(query):
            return FakeResponse()

        self.fake_engine.aquery = mock_aquery
        self.fake_index.as_query_engine.return_value = self.fake_engine

        app.dependency_overrides[get_index] = lambda: self.fake_index
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch('router.response.get_prompt_by_name')
    @patch('router.response.get_response_synthesizer')
    def test_query_success_default_mode(self, mock_synth, mock_prompt):
        mock_prompt.return_value = "You are a helpful assistant."
        mock_synth.return_value = MagicMock()

        response = self.client.post(
            "/response/test_index/query",
            data={
                "response_mode": "compact",
                "prompt_type": "QA_PROMPT",
                "query": "what is this?",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "mock answer"})
        mock_prompt.assert_called_once()
        mock_synth.assert_called_once_with(response_mode="compact")
        self.fake_index.as_query_engine.assert_called_once()

    @patch('router.response.get_prompt_by_name')
    @patch('router.response.get_response_synthesizer')
    def test_query_with_refine_and_condense(self, mock_synth, mock_prompt):
        mock_prompt.return_value = "Custom prompt template."
        mock_synth.return_value = MagicMock()

        response = self.client.post(
            "/response/test_index/query",
            data={
                "response_mode": "refine",
                "prompt_type": "CONDENSE_QUESTION_PROMPT",
                "query": "another question",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"response": "mock answer"})
        mock_synth.assert_called_once_with(response_mode="refine")


if __name__ == '__main__':
    unittest.main()