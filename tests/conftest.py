"""Shared pytest fixtures for CUITCCA tests."""
import os
import sys
from unittest.mock import MagicMock

import pytest

# Ensure backend/app is on sys.path
_APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'app')
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)


class FakeIndex:
    """Reusable fake LlamaIndex VectorStoreIndex for testing."""
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

    def as_query_engine(self, **kwargs):
        engine = MagicMock()
        engine.aquery = MagicMock(return_value=MagicMock(response="test answer"))
        return engine


@pytest.fixture
def fake_index():
    return FakeIndex()


@pytest.fixture
def fake_index_factory():
    def _make(index_id='test-index'):
        return FakeIndex(index_id)
    return _make
