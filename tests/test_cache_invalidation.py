"""缓存失效测试：覆盖索引修改后混合检索器缓存和索引锁的行为。"""
import asyncio
import unittest
from unittest.mock import MagicMock, patch

import pytest

import tests._pathsetup  # noqa: F401
from handlers.hybrid_retriever import (
    _hybrid_retriever_cache,
    build_retriever_for_index,
    invalidate_hybrid_retriever_cache,
)
from handlers.index_crud import _get_index_lock, _index_locks, _index_locks_guard


class HybridRetrieverCacheInvalidationTest(unittest.TestCase):
    def setUp(self):
        invalidate_hybrid_retriever_cache()

    def tearDown(self):
        invalidate_hybrid_retriever_cache()

    def test_invalidate_clears_all_cached_entries(self):
        """invalidate_hybrid_retriever_cache 应清空所有缓存条目"""
        _hybrid_retriever_cache[("idx1", 5)] = MagicMock()
        _hybrid_retriever_cache[("idx2", 10)] = MagicMock()
        self.assertEqual(len(_hybrid_retriever_cache), 2)

        invalidate_hybrid_retriever_cache()

        self.assertEqual(len(_hybrid_retriever_cache), 0)

    @patch('handlers.hybrid_retriever.load_env')
    @patch('handlers.hybrid_retriever._build_hybrid_retriever')
    def test_cache_key_includes_top_k(self, mock_build, mock_load_env):
        """缓存 key 必须包含 similarity_top_k，否则不同 top_k 会拿到错误的结果"""
        mock_load_env.HYBRID_RETRIEVAL_ENABLED = True
        fake_index = MagicMock()
        fake_index.index_id = "test-idx"

        retriever1 = MagicMock()
        retriever2 = MagicMock()
        mock_build.side_effect = [retriever1, retriever2]

        r1 = build_retriever_for_index(fake_index, 5)
        r2 = build_retriever_for_index(fake_index, 10)

        self.assertIs(r1, retriever1)
        self.assertIs(r2, retriever2)
        self.assertEqual(mock_build.call_count, 2)

    @patch('handlers.hybrid_retriever.load_env')
    @patch('handlers.hybrid_retriever._build_hybrid_retriever')
    def test_cache_returns_same_instance_for_same_key(self, mock_build, mock_load_env):
        """相同 (index_id, top_k) 应返回缓存的同一实例"""
        mock_load_env.HYBRID_RETRIEVAL_ENABLED = True
        fake_index = MagicMock()
        fake_index.index_id = "test-idx"
        retriever = MagicMock()
        mock_build.return_value = retriever

        r1 = build_retriever_for_index(fake_index, 5)
        r2 = build_retriever_for_index(fake_index, 5)

        self.assertIs(r1, r2)
        self.assertEqual(mock_build.call_count, 1)

    @patch('handlers.hybrid_retriever.load_env')
    @patch('handlers.hybrid_retriever._build_hybrid_retriever')
    def test_invalidate_forces_rebuild_on_next_call(self, mock_build, mock_load_env):
        """缓存失效后，下次调用应重新构建 retriever"""
        mock_load_env.HYBRID_RETRIEVAL_ENABLED = True
        fake_index = MagicMock()
        fake_index.index_id = "test-idx"

        retriever1 = MagicMock()
        retriever2 = MagicMock()
        mock_build.side_effect = [retriever1, retriever2]

        r1 = build_retriever_for_index(fake_index, 5)
        invalidate_hybrid_retriever_cache()
        r2 = build_retriever_for_index(fake_index, 5)

        self.assertIsNot(r1, r2)
        self.assertEqual(mock_build.call_count, 2)


class IndexLockTest(unittest.IsolatedAsyncioTestCase):
    """索引级锁测试：确保并发操作同一索引时使用正确的锁"""

    async def asyncSetUp(self):
        _index_locks.clear()

    async def asyncTearDown(self):
        _index_locks.clear()

    async def test_get_index_lock_returns_same_lock_for_same_id(self):
        """相同 index_id 应返回同一个锁实例"""
        lock1 = await _get_index_lock("idx-A")
        lock2 = await _get_index_lock("idx-A")
        self.assertIs(lock1, lock2)

    async def test_get_index_lock_returns_different_locks_for_different_ids(self):
        """不同 index_id 应返回不同的锁实例"""
        lock1 = await _get_index_lock("idx-A")
        lock2 = await _get_index_lock("idx-B")
        self.assertIsNot(lock1, lock2)

    async def test_concurrent_get_index_lock_is_safe(self):
        """并发获取同一 index_id 的锁不应创建多个实例"""
        lock_a, lock_b = await asyncio.gather(
            _get_index_lock("concurrent-idx"),
            _get_index_lock("concurrent-idx"),
        )
        self.assertIs(lock_a, lock_b)

    async def test_lock_serializes_concurrent_access(self):
        """锁应串行化对同一索引的并发访问"""
        lock = await _get_index_lock("test-serialize")
        execution_order = []

        async def task(name):
            async with lock:
                execution_order.append(f"{name}-start")
                await asyncio.sleep(0.01)
                execution_order.append(f"{name}-end")

        await asyncio.gather(task("A"), task("B"))

        # A 和 B 不应交叉执行
        a_start = execution_order.index("A-start")
        a_end = execution_order.index("A-end")
        b_start = execution_order.index("B-start")
        b_end = execution_order.index("B-end")
        self.assertEqual(a_end, a_start + 1)
        self.assertEqual(b_end, b_start + 1)


if __name__ == '__main__':
    unittest.main()
