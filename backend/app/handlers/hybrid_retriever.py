"""混合检索：dense（现有向量检索）+ BM25（jieba 分词），RRF 融合。

## 为什么不用 llama_index.retrievers.bm25.BM25Retriever

那个类的 ``tokenizer`` 参数在当前锁定版本（``llama-index-retrievers-bm25``
曾经装过 0.7.1，现已移除）里是**废弃且完全不生效**的死代码：传了只会打印一条
deprecation warning，然后被丢弃，分词仍然走内置正则
``(?u)\\b\\w\\w+\\b`` —— 这个正则对连续中文字符不产生词边界（``\\w`` 在
Unicode 模式下匹配所有 CJK 字符，中间没有空格就没有 ``\\b``），一整句中文会
被当成一个 token，BM25 的词频匹配直接失效。

这里改用 ``bm25s``（前者的底层依赖）+ jieba 自己实现一个轻量 retriever，
分词、建索引、查询全程用 jieba，不依赖那个失效的钩子。

## 节点来源：Chroma 而不是任何 docstore

``handlers/ingestion_pipeline.py`` 新增的持久化 docstore（见
``handlers/vector_store.py::load_or_create_docstore``）只保证增量摄取的
upsert 判断（doc_id -> 内容 hash），不保证包含某个索引历史上所有节点。
Chroma collection 本身才是"这个索引当前实际有哪些 chunk"的唯一可信来源，
所以 BM25 语料用 ``ChromaVectorStore.get_nodes(None)``（这是该 vector store
类已有的公开方法，内部走 ``metadata_dict_to_node`` 正确还原原文，不是我们
自己拼 Chroma 的 ``collection.get()`` 再重新发明一遍）现取现建。
"""
from __future__ import annotations

# load_env.X 属性访问而不是 from...import：reload_env_variables() 热重载改的
# 是 configs.load_env 模块内的变量，from...import 在导入时就把值拷贝进了当前
# 命名空间，之后源模块改了值这里感知不到（同样的坑见
# handlers/graph_builder.py 顶部注释）。
import configs.load_env as load_env
import jieba
from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
from llama_index.core.schema import BaseNode, NodeWithScore, QueryBundle
from llama_index.vector_stores.chroma import ChromaVectorStore


def jieba_tokenize(text: str) -> list[str]:
    return [tok for tok in jieba.lcut(text) if tok.strip()]


class JiebaBM25Retriever(BaseRetriever):
    """用 jieba 分词喂给 bm25s 的 BM25 检索器。

    检索到的 ``NodeWithScore.node`` 永远是传入的原始 node 对象（保留原文、
    metadata），分词只用于建索引和查询打分，不会把"分词后空格拼接的文本"
    误当成节点内容返回给上层——这是刻意避开 BM25Retriever 那条
    node_to_metadata_dict/model_dump() 还原路径可能引入的类似问题。
    """

    def __init__(self, nodes: list[BaseNode], similarity_top_k: int = 5):
        import bm25s

        self._nodes = list(nodes)
        self._similarity_top_k = max(1, min(similarity_top_k, len(self._nodes))) if self._nodes else 0
        self._bm25 = None
        if self._nodes:
            corpus_tokens = [jieba_tokenize(n.get_content()) for n in self._nodes]
            self._bm25 = bm25s.BM25()
            self._bm25.index(corpus_tokens, show_progress=False)
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        if self._bm25 is None:
            return []
        query_tokens = jieba_tokenize(query_bundle.query_str)
        if not query_tokens:
            return []
        indexes, scores = self._bm25.retrieve(
            [query_tokens], k=self._similarity_top_k, show_progress=False
        )
        return [
            NodeWithScore(node=self._nodes[int(idx)], score=float(score))
            for idx, score in zip(indexes[0], scores[0], strict=True)
            if score > 0
        ]


_hybrid_retriever_cache: dict[tuple[str, int], BaseRetriever] = {}


def invalidate_hybrid_retriever_cache() -> None:
    _hybrid_retriever_cache.clear()


# 每路（dense/BM25）召回宽度相对最终 top_k 的放大倍数，以及召回下限。
# 关键原因：QueryFusionRetriever 不会替子 retriever 加宽召回——每个子
# retriever 用自己构造时固定的 similarity_top_k 去召回，融合完再按
# QueryFusionRetriever 自己的 similarity_top_k 截断。如果两路都只召回最终
# 需要的这么多条，会出现"某一路的真正相关文档因为该路排名恰好在截断线以外、
# 根本没进入候选池"的情况——RRF 没机会看到它，等于白丢（用真实语料 smoke
# 测试过：similarity_top_k=2 时向量侧因为分数打平截断，命中的文档被截没了，
# 融合结果里完全消失）。跟现有 rerank 的 RERANK_RECALL_K/RERANK_TOP_N 是
# 同一个道理：先宽召回，后窄截断。
_RECALL_MULTIPLIER = 4
_RECALL_FLOOR = 20


def _build_hybrid_retriever(index: VectorStoreIndex, similarity_top_k: int) -> BaseRetriever:
    # isinstance 检查放在最前面：非 Chroma 场景（目前生产只有 Chroma，这里
    # 只是防御性兜底）直接退化成纯向量检索，不要在判断"能不能做混合"之前就
    # 先花一次 as_retriever(recall_k) 的调用——那次调用在这个分支里注定被
    # 丢弃，没有意义。
    vector_store = index.vector_store
    if not isinstance(vector_store, ChromaVectorStore):
        return index.as_retriever(similarity_top_k=similarity_top_k)

    nodes = vector_store.get_nodes(None)
    if not nodes:
        return index.as_retriever(similarity_top_k=similarity_top_k)

    recall_k = max(similarity_top_k * _RECALL_MULTIPLIER, _RECALL_FLOOR)
    vector_retriever = index.as_retriever(similarity_top_k=recall_k)
    bm25_retriever = JiebaBM25Retriever(nodes=nodes, similarity_top_k=recall_k)

    return QueryFusionRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        mode=FUSION_MODES.RECIPROCAL_RANK,
        similarity_top_k=similarity_top_k,
        # num_queries 必须显式设成 1：QueryFusionRetriever 默认 4，会用 LLM
        # 生成 3 个额外查询变体——不设置这个会给每次检索偷偷插入意料之外的
        # LLM 调用（延迟和费用都不是我们要的）。
        num_queries=1,
    )


def build_retriever_for_index(index: VectorStoreIndex, similarity_top_k: int) -> BaseRetriever:
    """检索构造的统一入口，四个查询路径（单索引/RouterQueryEngine 多索引
    tools/QAWorkflow/``/query`` 接口）都应该调这个函数，而不是各自直接调
    ``index.as_retriever()``——开关状态由这里一处判断，跟
    ``utils.rerank.ConditionalRerankPostprocessor`` 内部自己判断
    ``RERANK_ENABLED`` 是同一个模式。

    ``HYBRID_RETRIEVAL_ENABLED`` 关闭时直接退化成普通向量检索，不触碰
    Chroma 的 ``get_nodes(None)``/BM25 构建，不引入额外开销。

    打开时按 (index_id, similarity_top_k) 缓存构造好的融合 retriever。缓存
    key 必须带 similarity_top_k，不能只用 index_id——否则跟
    ``graph_builder.compose_graph_query_engine`` 修过的那个坑一样：不同调用点
    传不同 top_k（比如生产主路径 5、``/query`` 接口 2）时，谁先调用就把那个
    top_k 对应的 retriever 永久缓存住，后面用另一个 top_k 调用的调用方会静默
    拿到错误 top_k 的结果。索引内容变化（上传/删除文档）后靠
    ``invalidate_hybrid_retriever_cache()`` 整体清空重建。
    """
    if not load_env.HYBRID_RETRIEVAL_ENABLED:
        return index.as_retriever(similarity_top_k=similarity_top_k)

    cache_key = (index.index_id, similarity_top_k)
    if cache_key not in _hybrid_retriever_cache:
        _hybrid_retriever_cache[cache_key] = _build_hybrid_retriever(index, similarity_top_k)
    return _hybrid_retriever_cache[cache_key]
