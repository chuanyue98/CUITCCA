import asyncio  # noqa: I001 (tests._pathsetup must precede handlers below)
from unittest.mock import MagicMock, patch

import pytest

import tests._pathsetup  # noqa: F401
from handlers import index_crud


class FakeIndex:
    def __init__(self):
        self.index_id = 'idx-async-test'
        self.summary = ''
        self.vector_store = MagicMock()


@pytest.mark.asyncio
async def test_insert_into_index_offloads_ingestion_to_thread():
    index = FakeIndex()

    with patch('handlers.vector_store.load_or_create_docstore', return_value=MagicMock()), \
         patch('handlers.vector_store.persist_docstore'), \
         patch('handlers.ingestion_pipeline.build_pipeline', return_value=MagicMock()), \
         patch('handlers.ingestion_pipeline.ingest_files') as mock_ingest_files, \
         patch('asyncio.to_thread', wraps=asyncio.to_thread) as mock_to_thread:
        await index_crud.insert_into_index(index, '/fake/path.txt', skip_summary=True)

    mock_ingest_files.assert_called_once()
    # the actual parse+embed+write work must go through asyncio.to_thread,
    # not run directly on the event loop thread.
    mock_to_thread.assert_called_once()
    assert mock_to_thread.call_args.args[0] is index_crud._ingest_and_persist
