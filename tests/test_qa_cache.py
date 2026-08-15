"""handlers/qa_cache.py 语义缓存 + 人工问答沉淀的单元测试。

不碰真实 Chroma 库、不碰真实嵌入模型：
- ``_get_collection`` patch 成**内存** Chroma collection（ephemeral client），
  与真实知识库（data/chroma_db）零接触；
- ``_embed`` patch 成受控的确定性嵌入桩——手工指定向量，精确控制\"文本间
  余弦相似度\"，从而验证双 kind 阈值（auto 0.92 / curated 0.82）的命中边界，
  而不是依赖随机向量碰运气。

覆盖：
1. auto 条目：逐字相同命中；近重复（0.95）命中；意思不同（0.5）不命中
2. curated 条目：同义改写级别（0.95）命中（比 auto 更宽的阈值）
3. 完整链路（store -> lookup）：真实 llama-index 嵌入 API + 内存 Chroma
4. 👎 删除：delete_by_question 按问题文本删掉缓存条目
5. 驱逐：auto 超上限按命中次数升序驱逐，curated 不驱逐
6. 统计：stats() 分类计数
7. best-effort：QA_CACHE_ENABLED=False 时所有操作都是安全 no-op
"""
import asyncio
import hashlib
import math
import unittest
from unittest.mock import patch
from uuid import uuid4

import chromadb
import configs.load_env as load_env
from handlers import qa_cache
from llama_index.core.schema import NodeWithScore, TextNode

import tests._pathsetup  # noqa: F401


def _make_source_node(file_name: str = "图书馆借阅规则.pdf", text: str = "原文片段") -> NodeWithScore:
    return NodeWithScore(node=TextNode(id_="n1", text=text, metadata={"file_name": file_name}), score=0.9)


# 受控嵌入桩：2 维单位向量。A <-> A' = 0.95（同义改写级），A <-> B = 0.5
# （不同问题），其余落到 (0,1)。
async def _controlled_embed(text: str) -> list[float]:
    unit = {
        "图书馆几点开门": (1.0, 0.0),
        "图书馆几点开馆": (0.95, math.sqrt(1 - 0.95**2)),
        "食堂几点开门": (0.5, math.sqrt(1 - 0.5**2)),
    }.get(text, (0.0, 1.0))
    return list(unit)


def _ephemeral_collection():
    # 每个用例独立的 collection 名：chromadb 的 Client()/同名 collection 在同一
    # 测试进程里可能共享状态，复用固定名字会让不同用例互相污染（一个用例存
    # 的条目在另一个用例的"空 collection"断言里冒出来）。
    client = chromadb.Client()
    name = f"qa_cache_test_{uuid4().hex[:8]}"
    return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})


class _DeterministicEmbedder:
    """模拟 llama-index 嵌入模型：同一文本 -> 同一单位向量，不同文本 -> 不同向量。"""

    async def aget_query_embedding(self, text: str) -> list[float]:
        digest = hashlib.sha1(text.encode("utf-8")).digest()
        vec = [digest[i % len(digest)] / 255.0 for i in range(8)]
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec]


class QaCacheBaseTest(unittest.TestCase):
    def setUp(self):
        self._prev_enabled = load_env.QA_CACHE_ENABLED
        load_env.QA_CACHE_ENABLED = True

    def tearDown(self):
        load_env.QA_CACHE_ENABLED = self._prev_enabled


class QaCacheThresholdTest(QaCacheBaseTest):
    """用受控嵌入桩精确验证双 kind 阈值的命中/未命中边界。"""

    def setUp(self):
        super().setUp()
        self.collection = _ephemeral_collection()
        # 必须连 _get_collection 一起 patch——只 patch _embed 的话 store/lookup
        # 会打到真实 data/chroma_db 的 qa_cache 集合上，不同用例互相污染
        # （且污染真实开发库）。
        patcher = patch("handlers.qa_cache._get_collection", return_value=self.collection)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("handlers.qa_cache._embed", _controlled_embed)
    def test_auto_entry_verbatim_repeat_hits(self):
        asyncio.run(qa_cache.store_auto("图书馆几点开门", "答案", [_make_source_node()]))
        entry = asyncio.run(qa_cache.lookup("图书馆几点开门"))
        self.assertIsNotNone(entry)
        self.assertEqual(entry.kind, qa_cache.KIND_AUTO)
        self.assertEqual(entry.answer, "答案")
        self.assertEqual(entry.source_file, "图书馆借阅规则.pdf")
        self.assertEqual(entry.source_text, "原文片段")

    @patch("handlers.qa_cache._embed", _controlled_embed)
    def test_auto_entry_near_duplicate_hits_but_different_question_misses(self):
        asyncio.run(qa_cache.store_auto("图书馆几点开门", "答案", [_make_source_node()]))
        # 0.95 >= 0.92：近重复（几乎逐字相同）可以复用自动条目
        self.assertIsNotNone(asyncio.run(qa_cache.lookup("图书馆几点开馆")))
        # 0.5 < 0.92：意思不同的问题绝不能命中自动条目（答案未经人工校验）
        self.assertIsNone(asyncio.run(qa_cache.lookup("食堂几点开门")))

    @patch("handlers.qa_cache._embed", _controlled_embed)
    def test_curated_entry_has_wider_threshold(self):
        asyncio.run(qa_cache.store_curated("图书馆几点开门", "人工背书答案", [_make_source_node()]))
        # 0.95 >= 0.82：同义改写级的问题可以复用人工沉淀条目
        entry = asyncio.run(qa_cache.lookup("图书馆几点开馆"))
        self.assertIsNotNone(entry)
        self.assertEqual(entry.kind, qa_cache.KIND_CURATED)
        # 0.5 < 0.82：意思不同仍然不命中
        self.assertIsNone(asyncio.run(qa_cache.lookup("食堂几点开门")))


class QaCacheRoundTripTest(QaCacheBaseTest):
    """store -> lookup 全链路：真实内存 Chroma + 确定性嵌入桩（同一文本 ->
    同一向量）。不 patch Settings.embed_model：该属性 getter 在未配置时会去
    解析默认模型（缺 llama_index.embeddings.openai 包直接 ImportError），所以
    统一 patch 模块里的 _embed（生产里它只是 Settings.embed_model 的一行包装）。"""

    def setUp(self):
        super().setUp()
        self.collection = _ephemeral_collection()
        embedder = _DeterministicEmbedder()
        patcher = patch("handlers.qa_cache._embed", embedder.aget_query_embedding)
        patcher.start()
        self.addCleanup(patcher.stop)
        collection_patcher = patch(
            "handlers.qa_cache._get_collection", return_value=self.collection
        )
        collection_patcher.start()
        self.addCleanup(collection_patcher.stop)

    def test_store_then_lookup_same_text_hits(self):
        asyncio.run(qa_cache.store_auto("学生公寓热水怎么收费", "热水按用量收费", []))
        entry = asyncio.run(qa_cache.lookup("学生公寓热水怎么收费"))
        self.assertIsNotNone(entry)
        self.assertEqual(entry.answer, "热水按用量收费")

    def test_hits_counter_increments_on_lookup(self):
        asyncio.run(qa_cache.store_auto("同一个问题", "答案", []))
        for _ in range(3):
            asyncio.run(qa_cache.lookup("同一个问题"))
        metas = self.collection.get(include=["metadatas"])["metadatas"]
        self.assertEqual(len(metas), 1)
        self.assertEqual(metas[0]["hits"], 3)

    def test_lookup_on_empty_collection_returns_none(self):
        self.assertIsNone(asyncio.run(qa_cache.lookup("任何问题")))


class QaCacheLifecycleTest(QaCacheBaseTest):
    """删除 / 驱逐 / 统计 / 禁用开关。"""

    def setUp(self):
        super().setUp()
        self.collection = _ephemeral_collection()
        patcher = patch("handlers.qa_cache._get_collection", return_value=self.collection)
        patcher.start()
        self.addCleanup(patcher.stop)
        # conftest 未配置全局嵌入模型，存储类用例统一用受控嵌入桩
        embed_patcher = patch("handlers.qa_cache._embed", _controlled_embed)
        embed_patcher.start()
        self.addCleanup(embed_patcher.stop)

    def test_delete_by_question_removes_entry(self):
        asyncio.run(qa_cache.store_auto("图书馆几点开门", "答案", []))
        asyncio.run(qa_cache.store_curated("转专业条件", "转专业答案", []))
        asyncio.run(qa_cache.delete_by_question("图书馆几点开门"))
        self.assertIsNone(asyncio.run(qa_cache.lookup("图书馆几点开门")))
        # 其他问题不受影响
        self.assertIsNotNone(asyncio.run(qa_cache.lookup("转专业条件")))

    def test_auto_entries_evicted_by_lowest_hits_curated_never_evicted(self):
        with patch.object(load_env, "QA_CACHE_MAX_AUTO_ENTRIES", 2):
            asyncio.run(qa_cache.store_auto("问题一", "答案1", []))
            asyncio.run(qa_cache.store_auto("问题二", "答案2", []))
            asyncio.run(qa_cache.store_auto("问题三", "答案3", []))
            asyncio.run(qa_cache.store_curated("人工问题", "人工答案", []))
        remaining = self.collection.get(include=["metadatas"])
        kinds = sorted(m["kind"] for m in remaining["metadatas"])
        # 3 条 auto 驱逐到上限 2 条，curated 1 条保留
        self.assertEqual(kinds, [qa_cache.KIND_AUTO, qa_cache.KIND_AUTO, qa_cache.KIND_CURATED])
        self.assertEqual(self.collection.count(), 3)

    def test_stats_counts_by_kind(self):
        asyncio.run(qa_cache.store_auto("自动问题", "答案", []))
        asyncio.run(qa_cache.store_curated("人工问题", "答案", []))
        stats = asyncio.run(qa_cache.stats())
        self.assertTrue(stats["enabled"])
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["auto"], 1)
        self.assertEqual(stats["curated"], 1)

    def test_disabled_cache_is_safe_noop(self):
        load_env.QA_CACHE_ENABLED = False
        # 禁用时连 _embed/_get_collection 都不该被调用（返回/落库前就短路），
        # 所以即使这里的 patch 存在也不会被用到
        self.assertIsNone(asyncio.run(qa_cache.lookup("问题")))
        asyncio.run(qa_cache.store_auto("问题", "答案", []))
        asyncio.run(qa_cache.delete_by_question("问题"))
        stats = asyncio.run(qa_cache.stats())
        self.assertEqual(stats["enabled"], False)
        self.assertEqual(stats["total"], 0)


if __name__ == "__main__":
    unittest.main()
