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


@pytest.fixture(autouse=True)
def _reset_rate_limit_store():
    """``main._rate_limit_store`` 同样是模块级全局状态，按 IP 累计请求时间戳。

    TestClient 发出的所有请求共用同一个 client host（``testclient``），所以整
    个测试会话里的请求会累加到同一个 IP 桶里。限流覆盖范围扩大到全部 LLM 端点
    （``main.is_llm_endpoint``）之后，多个测试文件加起来很容易突破 30 次/60 秒
    的阈值，于是后面的用例开始收到 429——失败信息指向被测端点，和真正的原因
    （前面的用例把配额用光了）毫无关系，极难排查。

    和上面的 retriever 缓存是同一类问题、同一种解法：autouse 清空，让每个用例
    从干净状态开始。
    """
    from main import _rate_limit_store

    _rate_limit_store.clear()
    yield
    _rate_limit_store.clear()


@pytest.fixture(autouse=True)
def _pin_admin_api_key_unset(monkeypatch):
    """测试进程内固定"未配置管理密钥"状态。

    ``configs.load_env`` 在导入时会执行 ``load_dotenv(override=True)``，把开发者
    本机 backend/.env 里的 CUITCCA_API_KEY 灌进 os.environ。一旦本机配了真实
    密钥（比如为了启用 /manage 配置页），所有不带 Bearer 头的受保护接口请求都会
    从原来的 503/放行变成 401，几十个对鉴权不敏感的用例集体翻车——失败信息指向
    被测端点，和真正的原因（本地 .env 内容）毫无关系。

    autouse + monkeypatch 保证每个用例运行时该变量都是空串；需要模拟"已配置"
    的用例（如 test_manage_env_auth、test_llm_config_router）自己用
    patch.dict/setenv 覆盖即可，monkeypatch 收尾时恢复。
    """
    monkeypatch.setenv('CUITCCA_API_KEY', '')
