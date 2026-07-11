import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import tests._pathsetup  # noqa: F401

import handlers.graph_builder
from handlers.graph_builder import (
    MultiIndexQueryEngine,
    compose_graph_chat_egine,
    compose_graph_query_engine,
    invalidate_query_engine_cache,
    summary_index,
)


class FakeIndex:
    def __init__(self, index_id="test-index"):
        self.index_id = index_id
        self.summary = ""


class MultiIndexQueryEngineInitTest(unittest.TestCase):
    def test_creates_with_indexes_snapshot(self):
        fake_indexes = [FakeIndex(), FakeIndex()]
        engine = MultiIndexQueryEngine(indexes_snapshot=fake_indexes)
        self.assertIs(engine._indexes_snapshot, fake_indexes)


class MultiIndexQueryEngineAqueryTest(unittest.TestCase):
    def setUp(self):
        self.fake_indexes = [FakeIndex("idx1"), FakeIndex("idx2")]
        self.engine = MultiIndexQueryEngine(indexes_snapshot=self.fake_indexes)

    @patch("handlers.graph_builder.Prompts")
    def test_returns_first_non_empty_response(self, mock_prompts):
        mock_prompts.QA_PROMPT = MagicMock()
        mock_prompts.REFINE_PROMPT = MagicMock()

        engine1 = AsyncMock()
        resp1 = MagicMock()
        resp1.__str__.return_value = ""
        engine1.aquery.return_value = resp1

        engine2 = AsyncMock()
        resp2 = MagicMock()
        resp2.__str__.return_value = "real answer"
        engine2.aquery.return_value = resp2

        self.fake_indexes[0].as_query_engine = MagicMock(return_value=engine1)
        self.fake_indexes[1].as_query_engine = MagicMock(return_value=engine2)

        result = asyncio.run(self.engine._aquery("test query"))
        self.assertEqual(str(result), "real answer")

    @patch("handlers.graph_builder.Prompts")
    def test_returns_empty_response_when_all_empty(self, mock_prompts):
        mock_prompts.QA_PROMPT = MagicMock()
        mock_prompts.REFINE_PROMPT = MagicMock()

        engine1 = AsyncMock()
        resp1 = MagicMock()
        resp1.__str__.return_value = ""
        engine1.aquery.return_value = resp1

        engine2 = AsyncMock()
        resp2 = MagicMock()
        resp2.__str__.return_value = "Empty Response"
        engine2.aquery.return_value = resp2

        self.fake_indexes[0].as_query_engine = MagicMock(return_value=engine1)
        self.fake_indexes[1].as_query_engine = MagicMock(return_value=engine2)

        result = asyncio.run(self.engine._aquery("test query"))
        self.assertEqual(str(result), "Empty Response")

    @patch("handlers.graph_builder.Prompts")
    def test_handles_exceptions_gracefully(self, mock_prompts):
        mock_prompts.QA_PROMPT = MagicMock()
        mock_prompts.REFINE_PROMPT = MagicMock()

        engine1 = AsyncMock()
        engine1.aquery.side_effect = Exception("engine failure")

        engine2 = AsyncMock()
        resp2 = MagicMock()
        resp2.__str__.return_value = "fallback answer"
        engine2.aquery.return_value = resp2

        self.fake_indexes[0].as_query_engine = MagicMock(return_value=engine1)
        self.fake_indexes[1].as_query_engine = MagicMock(return_value=engine2)

        result = asyncio.run(self.engine._aquery("test query"))
        self.assertEqual(str(result), "fallback answer")


class ComposeGraphChatEngineTest(unittest.TestCase):
    @patch("handlers.graph_builder.indexes", new_callable=list)
    @patch("handlers.graph_builder.CondenseQuestionChatEngine")
    @patch("handlers.graph_builder.Prompts")
    def test_creates_condense_question_chat_engine(self, mock_prompts, mock_chat_engine, mock_indexes):
        mock_prompts.CONDENSE_QUESTION_PROMPT = MagicMock()
        mock_prompts.QA_PROMPT = MagicMock()
        mock_prompts.REFINE_PROMPT = MagicMock()

        fake_engine = MagicMock()
        mock_chat_engine.from_defaults.return_value = fake_engine

        result = compose_graph_chat_egine()

        self.assertIs(result, fake_engine)
        mock_chat_engine.from_defaults.assert_called_once()


class ComposeGraphQueryEngineTest(unittest.TestCase):
    def setUp(self):
        invalidate_query_engine_cache()

    @patch("handlers.graph_builder.indexes", new_callable=list)
    def test_returns_cached_query_engine(self, mock_indexes):
        mock_indexes.extend([FakeIndex()])

        engine1 = compose_graph_query_engine()
        engine2 = compose_graph_query_engine()

        self.assertIs(engine1, engine2)


class InvalidateQueryEngineCacheTest(unittest.TestCase):
    def test_clears_cache(self):
        fake_indexes = [FakeIndex()]
        engine = MultiIndexQueryEngine(indexes_snapshot=fake_indexes)
        handlers.graph_builder._query_engine_cache = engine

        invalidate_query_engine_cache()

        self.assertIsNone(handlers.graph_builder._query_engine_cache)


class SummaryIndexTest(unittest.TestCase):
    @patch("handlers.graph_builder.Prompts")
    def test_returns_summary_string(self, mock_prompts):
        mock_prompts.QA_PROMPT = MagicMock()
        mock_prompts.REFINE_PROMPT = MagicMock()

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