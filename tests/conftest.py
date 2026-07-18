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


@pytest.fixture(autouse=True)
def _reset_hybrid_retriever_cache():
    """handlers.hybrid_retriever 按 (index_id, top_k) 缓存构造好的 retriever，
    是模块级全局状态。不同测试文件/用例经常复用同样的字面量 index_id（比如
    "idx1"、"test-index"）指向不同的 fake/mock 对象，如果不在每个用例之间
    清空，会出现"这个用例其实拿到了上一个用例缓存下来的假 retriever，而不是
    本用例真正构造的那个"——断言失败但报错看起来毫不相关。autouse，不需要每个
    测试文件自己记得调用。"""
    from handlers.hybrid_retriever import invalidate_hybrid_retriever_cache

    invalidate_hybrid_retriever_cache()
    yield
    invalidate_hybrid_retriever_cache()
