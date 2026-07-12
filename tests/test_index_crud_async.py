import asyncio
from unittest.mock import MagicMock, patch

import pytest

import tests._pathsetup  # noqa: F401
from handlers import index_crud


class FakeIndex:
    def __init__(self):
        self.index_id = 'idx-async-test'
        self.summary = ''
        self.inserted = []

    def insert_nodes(self, nodes):
        self.inserted.extend(nodes)


@pytest.mark.asyncio
async def test_insert_into_index_offloads_parsing_and_embedding():
    index = FakeIndex()
    fake_nodes = [MagicMock()]

    with patch('utils.llama.get_nodes_from_file', return_value=fake_nodes) as mock_get_nodes, \
         patch('asyncio.to_thread', wraps=asyncio.to_thread) as mock_to_thread, \
         patch.object(index_crud, 'summary_index', new=None, create=True):
        # summary skipped so we only assert the parse+insert offload
        await index_crud.insert_into_index(index, '/fake/path.txt', skip_summary=True)

    mock_get_nodes.assert_called_once_with('/fake/path.txt')
    assert index.inserted == fake_nodes
    # both the parse call and the insert_nodes call must go through asyncio.to_thread
    assert mock_to_thread.call_count >= 2
