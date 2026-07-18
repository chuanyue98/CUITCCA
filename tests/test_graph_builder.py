import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from handlers.graph_builder import summary_index

import tests._pathsetup  # noqa: F401


class FakeIndex:
    def __init__(self, index_id="test-index"):
        self.index_id = index_id
        self.summary = ""
        self.as_query_engine = MagicMock(return_value=MagicMock())
        self.as_retriever = MagicMock(return_value=MagicMock())
        self.vector_store = MagicMock()


class SummaryIndexTest(unittest.TestCase):
    def test_returns_summary_string(self):
        mock_engine = AsyncMock()
        resp = MagicMock()
        resp.__str__.return_value = "summary text with spaces and newlines"
        mock_engine.aquery.return_value = resp

        index = FakeIndex()
        index.as_query_engine = MagicMock(return_value=mock_engine)

        result = asyncio.run(summary_index(index))

        self.assertEqual(result, "summary text with spaces and newlines")


if __name__ == "__main__":
    unittest.main()
