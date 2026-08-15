"""backend/app/handlers/auto_router.py 的测试。

覆盖：
1. route_query 的判定逻辑：
   - 检索为空 -> agent。
   - 检索异常 -> 降级路由到 agent（不让异常往上传播）。
   - 重排后 top1 分数 >= AUTO_ROUTE_SCORE_THRESHOLD -> standard。
   - 重排后 top1 分数 < AUTO_ROUTE_SCORE_THRESHOLD -> agent。
   - RERANK_ENABLED=False 时只看"是否检索到内容"，不比分数阈值（即使
     RRF 分数低于阈值，只要非空就应该走 standard——因为这时分数没有区分度，
     拿它判断等于随机路由）。
   - 问题压缩失败时降级用原始 query（复用 condense_query 的降级行为），
     不影响路由继续往下走。
   - RouteDecision 携带的 nodes/query_str 就是路由过程中已经算出来的结果，
     调用方可以直接复用，不需要重新检索。
2. generate_followup_suggestions：
   - 没有检索节点时直接返回空列表，不调用 LLM。
   - 正常解析 LLM 输出的 JSON 数组。
   - LLM 调用失败/输出不是合法 JSON 时静默降级为空列表。
   - 输出条数超过上限时被截断。

全部用注入的 FakeRetriever / RecordingLLM，不碰真实索引、不联网、不需要
真实的 cross-encoder 重排模型。
"""
from unittest.mock import patch

import pytest

import tests._pathsetup  # noqa: F401


def _make_node(text: str, file_name: str = "doc.txt", score: float | None = 0.9):
    from llama_index.core.schema import NodeWithScore, TextNode

    return NodeWithScore(node=TextNode(text=text, metadata={"file_name": file_name}), score=score)


class FakeRetriever:
    """返回固定 nodes（或抛异常）的假 retriever，记录被传了什么 query。"""

    def __init__(self, nodes=None, exc: Exception | None = None):
        self._nodes = nodes or []
        self._exc = exc
        self.calls: list[str] = []

    async def aretrieve(self, query_bundle):
        self.calls.append(query_bundle.query_str)
        if self._exc is not None:
            raise self._exc
        return self._nodes


class RecordingLLM:
    """极简假 LLM：只实现 auto_router 用到的 acomplete。"""

    def __init__(self, response: str | None = None, exc: Exception | None = None):
        self._response = response
        self._exc = exc
        self.received_prompts: list[str] = []

    async def acomplete(self, prompt: str, **kwargs):
        from llama_index.core.base.llms.types import CompletionResponse

        self.received_prompts.append(prompt)
        if self._exc is not None:
            raise self._exc
        return CompletionResponse(text=self._response or "")


# ── route_query ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_query_empty_retrieval_goes_to_agent():
    import configs.load_env as load_env
    from handlers.auto_router import MODE_AGENT, route_query

    retriever = FakeRetriever(nodes=[])

    with patch.object(load_env, "RERANK_ENABLED", True):
        decision = await route_query("图书馆几点开门", retriever=retriever)

    assert decision.mode == MODE_AGENT
    assert decision.nodes == []
    assert decision.query_str == "图书馆几点开门"
    assert "未直接检索到" in decision.reason or "检索" in decision.reason


@pytest.mark.asyncio
async def test_route_query_retrieval_error_falls_back_to_agent():
    """检索抛异常时不能让整个路由判定挂掉：降级到 agent，不向上抛异常。"""
    from handlers.auto_router import MODE_AGENT, route_query

    retriever = FakeRetriever(exc=RuntimeError("index boom"))

    decision = await route_query("学校的校训是什么", retriever=retriever)

    assert decision.mode == MODE_AGENT
    assert decision.nodes == []
    assert "失败" in decision.reason


@pytest.mark.asyncio
async def test_route_query_high_confidence_goes_to_standard():
    """重排后 top1 >= 阈值：走 standard，RouteDecision 带上已经检索好的 nodes。"""
    import configs.load_env as load_env
    from handlers.auto_router import MODE_STANDARD, route_query

    nodes = [_make_node("图书馆开馆规则原文", score=0.9)]
    retriever = FakeRetriever(nodes=nodes)

    with patch.object(load_env, "RERANK_ENABLED", True), \
         patch.object(load_env, "AUTO_ROUTE_SCORE_THRESHOLD", 0.6), \
         patch.object(load_env, "RERANK_TOP_N", 5):
        decision = await route_query("图书馆几点开门", retriever=retriever)

    assert decision.mode == MODE_STANDARD
    assert decision.nodes == nodes
    assert decision.query_str == "图书馆几点开门"
    assert retriever.calls == ["图书馆几点开门"]


@pytest.mark.asyncio
async def test_route_query_low_confidence_goes_to_agent():
    """重排后 top1 < 阈值：走 agent，但 nodes 仍然带出去（agent 分支目前不复用
    它，但保留这份中间结果给调用方/日志展示用，不能因为路由到 agent 就丢弃）。"""
    import configs.load_env as load_env
    from handlers.auto_router import MODE_AGENT, route_query

    nodes = [_make_node("不太相关的内容", score=0.3)]
    retriever = FakeRetriever(nodes=nodes)

    with patch.object(load_env, "RERANK_ENABLED", True), \
         patch.object(load_env, "AUTO_ROUTE_SCORE_THRESHOLD", 0.6), \
         patch.object(load_env, "RERANK_TOP_N", 5):
        decision = await route_query("一个语料没覆盖的问题", retriever=retriever)

    assert decision.mode == MODE_AGENT
    assert decision.nodes == nodes
    assert "0.30" in decision.reason or "置信度" in decision.reason


@pytest.mark.asyncio
async def test_route_query_rerank_disabled_only_checks_emptiness():
    """RERANK_ENABLED=False 时 nodes 上的分数是没有区分度的 RRF 融合分（实测
    覆盖/未覆盖的问题都落在 0.02~0.03），不能拿它跟 AUTO_ROUTE_SCORE_THRESHOLD
    比——即使分数远低于阈值，只要检索到内容就应该走 standard。"""
    import configs.load_env as load_env
    from handlers.auto_router import MODE_STANDARD, route_query

    # 分数故意设得比 AUTO_ROUTE_SCORE_THRESHOLD 低很多，模拟真实的 RRF 融合分。
    nodes = [_make_node("内容", score=0.03)]
    retriever = FakeRetriever(nodes=nodes)

    with patch.object(load_env, "RERANK_ENABLED", False), \
         patch.object(load_env, "AUTO_ROUTE_SCORE_THRESHOLD", 0.6), \
         patch.object(load_env, "RERANK_TOP_N", 5):
        decision = await route_query("任意问题", retriever=retriever)

    assert decision.mode == MODE_STANDARD
    assert decision.nodes == nodes


@pytest.mark.asyncio
async def test_route_query_condense_failure_falls_back_to_raw_query():
    """chat_history 非空但压缩 LLM 调用失败：降级用原始 query 继续检索/路由，
    不让路由判定本身失败。"""
    import configs.load_env as load_env
    from handlers.auto_router import MODE_STANDARD, route_query
    from llama_index.core.base.llms.types import ChatMessage, MessageRole

    nodes = [_make_node("内容", score=0.9)]
    retriever = FakeRetriever(nodes=nodes)
    llm = RecordingLLM(exc=RuntimeError("condense boom"))
    history = [ChatMessage(role=MessageRole.USER, content="之前问过的问题")]

    with patch.object(load_env, "RERANK_ENABLED", True), \
         patch.object(load_env, "AUTO_ROUTE_SCORE_THRESHOLD", 0.6), \
         patch.object(load_env, "RERANK_TOP_N", 5):
        decision = await route_query("那 xx 呢？", chat_history=history, retriever=retriever, llm=llm)

    # 压缩确实被尝试调用过（不是被跳过），只是失败了，降级用了原始 query
    assert len(llm.received_prompts) == 1
    assert decision.query_str == "那 xx 呢？"
    assert retriever.calls == ["那 xx 呢？"]
    assert decision.mode == MODE_STANDARD


@pytest.mark.asyncio
async def test_route_query_empty_chat_history_skips_condense_llm_call():
    """chat_history 为空时零 LLM 调用——路由判定本身不应该比标准问答多付一次
    压缩往返。"""
    from handlers.auto_router import route_query

    nodes = [_make_node("内容", score=0.9)]
    retriever = FakeRetriever(nodes=nodes)
    llm = RecordingLLM(response="不应该被用到")

    await route_query("学校的校训是什么", retriever=retriever, llm=llm)

    assert llm.received_prompts == []


# ── generate_followup_suggestions ───────────────────────────────────


@pytest.mark.asyncio
async def test_generate_followup_suggestions_no_nodes_returns_empty_without_llm_call():
    from handlers.auto_router import generate_followup_suggestions

    llm = RecordingLLM(response='["不应该被用到"]')

    suggestions = await generate_followup_suggestions("问题", [], llm=llm)

    assert suggestions == []
    assert llm.received_prompts == []


@pytest.mark.asyncio
async def test_generate_followup_suggestions_parses_json_array():
    from handlers.auto_router import generate_followup_suggestions

    nodes = [_make_node("图书馆本科生可借 10 册，硕士生可借 15 册")]
    llm = RecordingLLM(response='["硕士生能借多少本书？", "图书馆几点闭馆？"]')

    suggestions = await generate_followup_suggestions("图书馆能借几本书", nodes, llm=llm)

    assert suggestions == ["硕士生能借多少本书？", "图书馆几点闭馆？"]
    assert len(llm.received_prompts) == 1
    assert "图书馆能借几本书" in llm.received_prompts[0]


@pytest.mark.asyncio
async def test_generate_followup_suggestions_strips_markdown_code_fence():
    """模型偶尔会不听话地包一层 ```json ... ``` 代码块，应该能剥掉再解析。"""
    from handlers.auto_router import generate_followup_suggestions

    nodes = [_make_node("一些内容")]
    llm = RecordingLLM(response='```json\n["追问一", "追问二"]\n```')

    suggestions = await generate_followup_suggestions("问题", nodes, llm=llm)

    assert suggestions == ["追问一", "追问二"]


@pytest.mark.asyncio
async def test_generate_followup_suggestions_llm_error_returns_empty_list():
    """LLM 调用失败：静默降级返回空列表，不向上抛异常。"""
    from handlers.auto_router import generate_followup_suggestions

    nodes = [_make_node("一些内容")]
    llm = RecordingLLM(exc=RuntimeError("llm boom"))

    suggestions = await generate_followup_suggestions("问题", nodes, llm=llm)

    assert suggestions == []


@pytest.mark.asyncio
async def test_generate_followup_suggestions_invalid_json_returns_empty_list():
    """LLM 输出不是合法 JSON（或不是字符串数组）时降级为空列表，不展示半成品。"""
    from handlers.auto_router import generate_followup_suggestions

    nodes = [_make_node("一些内容")]
    llm = RecordingLLM(response="这不是 JSON，是模型自由发挥的一段话")

    suggestions = await generate_followup_suggestions("问题", nodes, llm=llm)

    assert suggestions == []


@pytest.mark.asyncio
async def test_generate_followup_suggestions_non_string_items_and_object_are_rejected():
    from handlers.auto_router import generate_followup_suggestions

    nodes = [_make_node("一些内容")]
    # 数组本身合法，但内容不是纯字符串数组 -> 过滤掉非字符串项
    llm = RecordingLLM(response='["合法追问", 123, null, "另一个合法追问"]')

    suggestions = await generate_followup_suggestions("问题", nodes, llm=llm)

    assert suggestions == ["合法追问", "另一个合法追问"]

    # 顶层不是数组（比如是个 JSON object）-> 整体判定失败，返回空列表
    llm2 = RecordingLLM(response='{"foo": "bar"}')
    suggestions2 = await generate_followup_suggestions("问题", nodes, llm=llm2)
    assert suggestions2 == []


@pytest.mark.asyncio
async def test_generate_followup_suggestions_truncated_to_max_count():
    from handlers.auto_router import FOLLOWUP_SUGGESTION_MAX_COUNT, generate_followup_suggestions

    nodes = [_make_node("一些内容")]
    too_many = [f"追问{i}" for i in range(FOLLOWUP_SUGGESTION_MAX_COUNT + 5)]
    import json as _json
    llm = RecordingLLM(response=_json.dumps(too_many, ensure_ascii=False))

    suggestions = await generate_followup_suggestions("问题", nodes, llm=llm)

    assert len(suggestions) == FOLLOWUP_SUGGESTION_MAX_COUNT


if __name__ == "__main__":
    pytest.main([__file__])
