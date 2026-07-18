"""backend/app/handlers/hybrid_retriever.py 的测试。

覆盖三块：
1. JiebaBM25Retriever：按 jieba 分词后的关键词重合度正确排序，返回的
   node 对象是原始节点（不是分词后拼接的文本）。
2. build_retriever_for_index：真实 Chroma collection 上端到端验证——尤其是
   similarity_top_k 很小时，两路召回宽度不足会把真正命中的文档在融合前就
   截没的回归测试（这是实现时用真实语料 smoke 测试出来的 bug）。
3. 按 (index_id, similarity_top_k) 缓存 + invalidate_hybrid_retriever_cache
   清空的行为。
"""
import tempfile
import unittest
from unittest.mock import patch

import tests._pathsetup  # noqa: F401


class JiebaBM25RetrieverTest(unittest.TestCase):
    def test_ranks_by_keyword_overlap_and_returns_original_nodes(self):
        from handlers.hybrid_retriever import JiebaBM25Retriever
        from llama_index.core.schema import QueryBundle, TextNode

        nodes = [
            TextNode(text="成都信息工程大学的校训是成于大气 信达天下", metadata={"file_name": "a.txt"}),
            TextNode(text="国家奖学金奖励标准为8000元每人每年", metadata={"file_name": "b.txt"}),
        ]
        retriever = JiebaBM25Retriever(nodes=nodes, similarity_top_k=2)

        results = retriever._retrieve(QueryBundle(query_str="成信大的校训是什么"))

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].node.metadata["file_name"], "a.txt")
        # 返回的是原始节点内容，不是分词后空格拼接的文本
        self.assertEqual(results[0].node.get_content(), nodes[0].get_content())

    def test_empty_nodes_returns_empty_results(self):
        from handlers.hybrid_retriever import JiebaBM25Retriever
        from llama_index.core.schema import QueryBundle

        retriever = JiebaBM25Retriever(nodes=[], similarity_top_k=5)
        self.assertEqual(retriever._retrieve(QueryBundle(query_str="随便问点什么")), [])


class BuildRetrieverForIndexTest(unittest.TestCase):
    def setUp(self):
        import chromadb
        import configs.load_env as load_env
        from handlers import hybrid_retriever

        hybrid_retriever.invalidate_hybrid_retriever_cache()
        self._tmp_dir = tempfile.mkdtemp()
        self.client = chromadb.PersistentClient(path=self._tmp_dir)
        self.addCleanup(self.client.clear_system_cache)
        self.addCleanup(hybrid_retriever.invalidate_hybrid_retriever_cache)

        # 这些用例测的是混合检索打开时的行为；开关关闭时的短路行为单独测。
        self._enabled_patcher = patch.object(load_env, "HYBRID_RETRIEVAL_ENABLED", True)
        self._enabled_patcher.start()
        self.addCleanup(self._enabled_patcher.stop)

    def _build_index(self, collection_name: str):
        from llama_index.core import Document, VectorStoreIndex
        from llama_index.core.embeddings import MockEmbedding
        from llama_index.vector_stores.chroma import ChromaVectorStore

        embed_model = MockEmbedding(embed_dim=8)
        collection = self.client.get_or_create_collection(collection_name)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store, embed_model=embed_model)
        index.set_index_id(collection_name)

        docs = [
            Document(text="成都信息工程大学的校训是成于大气 信达天下", metadata={"file_name": "a.txt"}),
            Document(text="国家奖学金奖励标准为8000元每人每年", metadata={"file_name": "b.txt"}),
            Document(text="学校勤工助学的工资标准是150到200元每人每月", metadata={"file_name": "c.txt"}),
        ]
        for d in docs:
            index.insert(d)
        return index

    def test_small_top_k_does_not_lose_the_matching_document(self):
        """回归测试：similarity_top_k 很小时，两路各自只召回 top_k 条会让
        RRF 融合前候选池就漏掉真正命中的文档（各路窄召回，融合再截断，而不是
        宽召回、融合后再截断）。"""
        from handlers.hybrid_retriever import build_retriever_for_index

        index = self._build_index("hybrid-small-topk")
        retriever = build_retriever_for_index(index, similarity_top_k=2)

        results = retriever.retrieve("成信大的校训是什么")

        file_names = [r.node.metadata["file_name"] for r in results]
        self.assertIn("a.txt", file_names)

    def test_caches_by_index_id_and_top_k(self):
        from handlers.hybrid_retriever import build_retriever_for_index

        index = self._build_index("hybrid-cache-test")

        retriever_a = build_retriever_for_index(index, similarity_top_k=2)
        retriever_a_again = build_retriever_for_index(index, similarity_top_k=2)
        retriever_b = build_retriever_for_index(index, similarity_top_k=5)

        self.assertIs(retriever_a, retriever_a_again)
        self.assertIsNot(retriever_a, retriever_b)

    def test_invalidate_cache_forces_rebuild(self):
        from handlers.hybrid_retriever import build_retriever_for_index, invalidate_hybrid_retriever_cache

        index = self._build_index("hybrid-invalidate-test")

        retriever_before = build_retriever_for_index(index, similarity_top_k=2)
        invalidate_hybrid_retriever_cache()
        retriever_after = build_retriever_for_index(index, similarity_top_k=2)

        self.assertIsNot(retriever_before, retriever_after)

    def test_empty_collection_falls_back_to_vector_retriever(self):
        from handlers.hybrid_retriever import build_retriever_for_index
        from llama_index.core import VectorStoreIndex
        from llama_index.core.embeddings import MockEmbedding
        from llama_index.core.retrievers import QueryFusionRetriever
        from llama_index.vector_stores.chroma import ChromaVectorStore

        collection = self.client.get_or_create_collection("hybrid-empty-test")
        vector_store = ChromaVectorStore(chroma_collection=collection)
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store, embed_model=MockEmbedding(embed_dim=8))
        index.set_index_id("hybrid-empty-test")

        retriever = build_retriever_for_index(index, similarity_top_k=2)

        self.assertNotIsInstance(retriever, QueryFusionRetriever)


class HybridRetrievalDisabledTest(unittest.TestCase):
    """HYBRID_RETRIEVAL_ENABLED 关闭时必须在 build_retriever_for_index 最外层
    就完全短路——不触碰 Chroma 的 get_nodes(None)、不构建 BM25，直接退化成
    普通向量检索。显式 patch 成 False（不依赖生产默认值当前是什么），否则
    这个用例真正验证的是"非 Chroma vector_store 的兜底分支"而不是"开关关闭"，
    两条分支凑巧走到同一行代码，不显式 patch 会掩盖这个区别。"""

    def test_disabled_flag_skips_hybrid_construction_entirely(self):
        from unittest.mock import MagicMock, patch

        import configs.load_env as load_env
        from handlers.hybrid_retriever import build_retriever_for_index

        fake_index = MagicMock()
        fake_index.index_id = "should-not-be-cached"
        fake_vector_retriever = MagicMock()
        fake_index.as_retriever.return_value = fake_vector_retriever

        with patch.object(load_env, "HYBRID_RETRIEVAL_ENABLED", False):
            result = build_retriever_for_index(fake_index, similarity_top_k=5)

        fake_index.as_retriever.assert_called_once_with(similarity_top_k=5)
        self.assertIs(result, fake_vector_retriever)
        # vector_store 完全没被碰过——没有触发 get_nodes(None)/BM25 构建
        fake_index.vector_store.get_nodes.assert_not_called()


if __name__ == "__main__":
    unittest.main()
