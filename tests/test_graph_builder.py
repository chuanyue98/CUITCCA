import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import handlers.graph_builder
from handlers.graph_builder import (
    MultiIndexQueryEngine,
    compose_graph_chat_egine,
    compose_graph_query_engine,
    invalidate_query_engine_cache,
    summary_index,
)

import tests._pathsetup  # noqa: F401


class FakeIndex:
    def __init__(self, index_id="test-index"):
        self.index_id = index_id
        self.summary = ""
        self.as_query_engine = MagicMock(return_value=MagicMock())


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

    @patch("handlers.graph_builder.indexes", new_callable=list)
    def test_caches_streaming_and_non_streaming_separately(self, mock_indexes):
        # Regression: the cache used to be a single slot keyed by nothing, so
        # whichever streaming value called compose_graph_query_engine() first
        # got stuck there forever, silently handing every later caller (of the
        # *other* streaming value) the wrong kind of engine.
        fake_index = FakeIndex()
        fake_index.as_query_engine = MagicMock(side_effect=lambda **kwargs: MagicMock())
        mock_indexes.extend([fake_index])

        non_streaming = compose_graph_query_engine(streaming=False)
        streaming = compose_graph_query_engine(streaming=True)

        self.assertIsNot(non_streaming, streaming)
        self.assertIs(compose_graph_query_engine(streaming=False), non_streaming)
        self.assertIs(compose_graph_query_engine(streaming=True), streaming)


class InvalidateQueryEngineCacheTest(unittest.TestCase):
    def test_clears_cache(self):
        fake_indexes = [FakeIndex()]
        engine = MultiIndexQueryEngine(indexes_snapshot=fake_indexes)
        handlers.graph_builder._query_engine_caches[False] = engine

        invalidate_query_engine_cache()

        self.assertEqual(handlers.graph_builder._query_engine_caches, {})


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
