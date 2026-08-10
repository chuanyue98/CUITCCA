"""backend/app/agents/tools.py 的测试。

覆盖每个工具函数的正常路径和异常路径：
1. search_knowledge_base：空 query 报错；index_name 指定但索引不存在；
   index_name 指定且存在时走 build_retriever_for_index + 单索引；不指定
   index_name 时复用 handlers.qa_workflow._build_retriever；结果里带
   node_id/score/file_name/source_url/text；正文过长会被截断并标记
   truncated；检索抛异常时返回结构化错误 JSON 而不是让异常往外传。
2. list_knowledge_bases：返回当前索引的 index_name + summary。
3. get_document_chunks_by_source：空 source 报错；index_name 指定但不存在；
   正常路径按 file_name/source_url 查 Chroma collection.get 并合并去重；
   max_chunks 会被 clamp 到 [1, 20]；Chroma 调用异常时返回结构化错误。
4. get_current_datetime：返回结构里带 date/time/weekday/iso_week/note，
   note 明确说明不了解校历。

全部用 patch 假索引/假 retriever/假 Chroma client，不碰真实索引、不联网。
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from agents import tools as agent_tools
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

import tests._pathsetup  # noqa: F401


def _make_node(text: str, file_name: str = "测试文档.txt", score: float = 0.9, node_id: str = "n1"):
    node = TextNode(text=text, id_=node_id, metadata={"file_name": file_name})
    return NodeWithScore(node=node, score=score)


class FakeRetriever:
    def __init__(self, nodes):
        self._nodes = nodes
        self.calls: list[str] = []

    async def aretrieve(self, query_bundle: QueryBundle):
        self.calls.append(query_bundle.query_str)
        return self._nodes


def _fake_index(index_id: str, summary: str | None = None):
    idx = MagicMock()
    idx.index_id = index_id
    if summary is not None:
        idx.summary = summary
    else:
        del idx.summary  # getattr(idx, "summary", None) 应该走 fallback 分支
    return idx


# ── search_knowledge_base ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_knowledge_base_rejects_empty_query():
    result = json.loads(await agent_tools.search_knowledge_base(query="   "))
    assert "error" in result


@pytest.mark.asyncio
async def test_search_knowledge_base_unknown_index_name_lists_available():
    with patch("agents.tools.get_index_by_name", return_value=None), \
            patch("agents.tools.indexes", [_fake_index("idx1"), _fake_index("idx2")]):
        result = json.loads(await agent_tools.search_knowledge_base(query="学校地址", index_name="不存在的索引"))

    assert "error" in result
    assert result["available_indexes"] == ["idx1", "idx2"]


@pytest.mark.asyncio
async def test_search_knowledge_base_with_index_name_uses_build_retriever_for_index():
    nodes = [_make_node("成都信息工程大学地址在成都", node_id="n1")]
    fake_retriever = FakeRetriever(nodes)
    fake_index = _fake_index("idx1")

    with patch("agents.tools.get_index_by_name", return_value=fake_index), \
            patch("agents.tools.build_retriever_for_index", return_value=fake_retriever) as mock_build, \
            patch("agents.tools.ConditionalRerankPostprocessor") as mock_rerank_cls:
        mock_rerank_cls.return_value.postprocess_nodes.return_value = nodes
        result = json.loads(
            await agent_tools.search_knowledge_base(query="学校地址", index_name="idx1", top_k=3)
        )

    mock_build.assert_called_once_with(fake_index, 3)
    assert fake_retriever.calls == ["学校地址"]
    assert result["result_count"] == 1
    entry = result["results"][0]
    assert entry["node_id"] == "n1"
    assert entry["file_name"] == "测试文档.txt"
    assert entry["score"] == 0.9
    assert "成都" in entry["text"]


@pytest.mark.asyncio
async def test_search_knowledge_base_without_index_name_uses_qa_workflow_build_retriever():
    """不指定 index_name 时应该复用 handlers.qa_workflow._build_retriever
    的 0/1/多索引选择逻辑，不是自己另写一套。"""
    nodes = [_make_node("一些内容")]
    fake_retriever = FakeRetriever(nodes)

    with patch("handlers.qa_workflow._build_retriever", return_value=fake_retriever) as mock_build:
        result = json.loads(await agent_tools.search_knowledge_base(query="随便问点什么"))

    mock_build.assert_called_once_with(top_k=None)
    assert fake_retriever.calls == ["随便问点什么"]
    assert result["result_count"] == 1


@pytest.mark.asyncio
async def test_search_knowledge_base_truncates_long_text():
    long_text = "字" * (agent_tools._MAX_SNIPPET_CHARS + 100)
    nodes = [_make_node(long_text)]
    fake_retriever = FakeRetriever(nodes)

    with patch("handlers.qa_workflow._build_retriever", return_value=fake_retriever):
        result = json.loads(await agent_tools.search_knowledge_base(query="q"))

    entry = result["results"][0]
    assert entry["truncated"] is True
    assert len(entry["text"]) == agent_tools._MAX_SNIPPET_CHARS


@pytest.mark.asyncio
async def test_search_knowledge_base_returns_empty_results_not_error_when_nothing_found():
    fake_retriever = FakeRetriever([])
    with patch("handlers.qa_workflow._build_retriever", return_value=fake_retriever):
        result = json.loads(await agent_tools.search_knowledge_base(query="查不到的东西"))

    assert result["result_count"] == 0
    assert result["results"] == []
    assert "error" not in result


@pytest.mark.asyncio
async def test_search_knowledge_base_swallows_retriever_exception():
    class BoomRetriever:
        async def aretrieve(self, query_bundle):
            raise RuntimeError("retriever exploded")

    with patch("handlers.qa_workflow._build_retriever", return_value=BoomRetriever()):
        result = json.loads(await agent_tools.search_knowledge_base(query="q"))

    assert "error" in result


# ── list_knowledge_bases ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_knowledge_bases_returns_names_and_summaries():
    idx_with_summary = _fake_index("idx1", summary="宿舍管理规定")
    idx_without_summary = _fake_index("idx2", summary=None)

    with patch("agents.tools.indexes", [idx_with_summary, idx_without_summary]):
        result = json.loads(await agent_tools.list_knowledge_bases())

    assert result["index_count"] == 2
    assert result["indexes"] == [
        {"index_name": "idx1", "summary": "宿舍管理规定"},
        {"index_name": "idx2", "summary": "知识库索引: idx2"},
    ]


@pytest.mark.asyncio
async def test_list_knowledge_bases_empty_when_no_indexes():
    with patch("agents.tools.indexes", []):
        result = json.loads(await agent_tools.list_knowledge_bases())
    assert result == {"index_count": 0, "indexes": []}


# ── get_document_chunks_by_source ────────────────────────────────────


def _fake_collection(get_return_by_key: dict[str, dict]):
    """按 where={key: value} 里的 key 返回不同结果的假 collection。"""
    collection = MagicMock()

    def _get(where=None, limit=None):
        key = next(iter(where))
        return get_return_by_key.get(key, {"ids": [], "documents": [], "metadatas": []})

    collection.get.side_effect = _get
    return collection


@pytest.mark.asyncio
async def test_get_document_chunks_by_source_rejects_empty_source():
    result = json.loads(await agent_tools.get_document_chunks_by_source(source="  "))
    assert "error" in result


@pytest.mark.asyncio
async def test_get_document_chunks_by_source_unknown_index_name():
    with patch("agents.tools.get_index_by_name", return_value=None), \
            patch("agents.tools.indexes", [_fake_index("idx1")]):
        result = json.loads(
            await agent_tools.get_document_chunks_by_source(source="a.txt", index_name="不存在")
        )
    assert "error" in result
    assert result["available_indexes"] == ["idx1"]


@pytest.mark.asyncio
async def test_get_document_chunks_by_source_merges_file_name_and_source_url_matches():
    collection = _fake_collection({
        "file_name": {"ids": ["n1"], "documents": ["原文内容 1"], "metadatas": [{"file_name": "a.txt"}]},
        "source_url": {
            "ids": ["n1", "n2"],
            "documents": ["原文内容 1", "原文内容 2"],
            "metadatas": [{"file_name": "a.txt"}, {"source_url": "http://x"}],
        },
    })
    fake_client = MagicMock()
    fake_client.get_collection.return_value = collection
    fake_index = _fake_index("idx1")

    with patch("agents.tools.indexes", [fake_index]), \
            patch("handlers.vector_store._get_client", return_value=fake_client):
        result = json.loads(
            await agent_tools.get_document_chunks_by_source(source="a.txt", max_chunks=5)
        )

    # n1 命中两次（file_name 和 source_url 两路查询都返回了它）应该被去重，
    # 最终应该是 n1 + n2 两条，不是三条。
    assert result["chunk_count"] == 2
    node_ids = {c["node_id"] for c in result["chunks"]}
    assert node_ids == {"n1", "n2"}
    assert all(c["index_name"] == "idx1" for c in result["chunks"])


@pytest.mark.asyncio
async def test_get_document_chunks_by_source_max_chunks_clamped_to_hard_limit():
    many_ids = [f"n{i}" for i in range(30)]
    collection = _fake_collection({
        "file_name": {
            "ids": many_ids,
            "documents": ["x"] * 30,
            "metadatas": [{"file_name": "a.txt"}] * 30,
        },
    })
    fake_client = MagicMock()
    fake_client.get_collection.return_value = collection

    with patch("agents.tools.indexes", [_fake_index("idx1")]), \
            patch("handlers.vector_store._get_client", return_value=fake_client):
        result = json.loads(
            await agent_tools.get_document_chunks_by_source(source="a.txt", max_chunks=999)
        )

    assert result["chunk_count"] <= agent_tools._HARD_MAX_CHUNKS


@pytest.mark.asyncio
async def test_get_document_chunks_by_source_returns_empty_when_no_match():
    collection = _fake_collection({})
    fake_client = MagicMock()
    fake_client.get_collection.return_value = collection

    with patch("agents.tools.indexes", [_fake_index("idx1")]), \
            patch("handlers.vector_store._get_client", return_value=fake_client):
        result = json.loads(await agent_tools.get_document_chunks_by_source(source="不存在的文件.txt"))

    assert result == {"source": "不存在的文件.txt", "chunk_count": 0, "chunks": []}


@pytest.mark.asyncio
async def test_get_document_chunks_by_source_swallows_client_exception():
    with patch("agents.tools.indexes", [_fake_index("idx1")]), \
            patch("handlers.vector_store._get_client", side_effect=RuntimeError("chroma down")):
        result = json.loads(await agent_tools.get_document_chunks_by_source(source="a.txt"))

    assert "error" in result


# ── get_current_datetime ─────────────────────────────────────────────


def test_get_current_datetime_shape_and_disclaimer():
    result = json.loads(agent_tools.get_current_datetime())

    assert set(result.keys()) == {"date", "time", "weekday", "iso_week", "note"}
    assert result["weekday"] in agent_tools._WEEKDAY_CN
    assert 1 <= result["iso_week"] <= 53
    assert "校历" in result["note"]
    assert "不了解" in result["note"]  # 明确写清楚这个工具不知道校历安排，不装作能查
