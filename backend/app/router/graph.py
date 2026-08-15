import json
import os
import secrets
import time
from collections import OrderedDict

from fastapi import APIRouter, Depends, Form, Request, WebSocket, WebSocketDisconnect
from handlers.index_crud import format_source_nodes_list
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from models.response import QueryResponse, QuerySourcesResponse
from starlette import status
from starlette.responses import JSONResponse, StreamingResponse
from utils.logger import customer_logger, error_logger, query_logger
from utils.security import require_api_key_if_configured

graph_app = APIRouter(dependencies=[Depends(require_api_key_if_configured)])

# 会话缓存最大容量
_MAX_SESSIONS = 200
_SESSION_TTL = 3600  # 1小时


class TTLCache:
    """简单的 TTL + LRU 缓存，替代裸 dict"""

    def __init__(self, max_size: int = _MAX_SESSIONS, ttl: int = _SESSION_TTL):
        self._data: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key):
        entry = self._data.get(key)
        if entry is None:
            return None
        if time.time() - entry[1] > self._ttl:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return entry[0]

    def set(self, key, value):
        self._data[key] = (value, time.time())
        self._data.move_to_end(key)
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)

    def __contains__(self, key):
        return self.get(key) is not None

    def __len__(self):
        return len(self._data)


def _client_id(request: Request) -> str:
    if hasattr(request.state, "session_id"):
        return request.state.session_id
    return request.cookies.get("session_id") or "unknown"


_chat_histories: TTLCache = TTLCache()
_last_query_response: TTLCache = TTLCache()


def _source_file_name(sn: NodeWithScore) -> str | None:
    """从来源节点 metadata 里取 file_name，防御性判型。

    正常路径 ``metadata['file_name']`` 是字符串（documents_from_file 写入），
    但节点 metadata 本质是任意 dict——非字符串值（或缺失）不该让整个
    ``/query_sources`` 响应序列化炸掉，一律降级成 None 由前端兜底展示
    "未知来源"。
    """
    raw = (sn.node.metadata or {}).get('file_name')
    return raw if isinstance(raw, str) else None


class _PrefetchedNodesRetriever(BaseRetriever):
    """占位 retriever：原样返回 auto_router 已经算好的 nodes，不重新检索。

    ``/ask_stream`` 的 standard 分支复用 ``handlers.auto_router.route_query()``
    路由判定时已经跑完的"压缩问题 -> 检索 -> 重排"结果——``QAWorkflow`` 支持
    注入 ``retriever=``（见 ``handlers/qa_workflow.py``），这里传一个忽略传入
    query、直接吐出预先算好的 nodes 的假 retriever，让 ``QAWorkflow.retrieve``
    step 走完它原有的（此时会因为 ``len(nodes) <= RERANK_TOP_N`` 而快速跳过
    的）rerank 分支，但不会真的对同一个问题重复打一次向量/混合检索。
    """

    def __init__(self, nodes: list[NodeWithScore]) -> None:
        self._nodes = nodes
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self._nodes

    async def _aretrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self._nodes


@graph_app.post("/create")
async def create_graph(request: Request):
    client_id = _client_id(request)
    _chat_histories.set(client_id, [])
    return {"status": "ok"}


@graph_app.post("/chat_stream")
async def chat_graph_stream(request: Request, query: str = Form(max_length=5000)):
    from handlers.qa_workflow import QAWorkflow, TokenEvent

    client_id = _client_id(request)
    history: list[ChatMessage] = list(_chat_histories.get(client_id) or [])
    query = query.strip()
    customer_logger.info(f"chat_stream: {query}")
    workflow = QAWorkflow(timeout=60)
    handler = workflow.run(query=query, chat_history=history, streaming=True)

    async def _token_gen():
        try:
            async for ev in handler.stream_events():
                if isinstance(ev, TokenEvent):
                    yield ev.token
            result = await handler
            _last_query_response.set(client_id, result.source_nodes)
            history.append(ChatMessage(role=MessageRole.USER, content=query))
            history.append(ChatMessage(role=MessageRole.ASSISTANT, content=result.response))
            _chat_histories.set(client_id, history)
        except Exception as e:
            error_logger.error(f"chat_stream error: {e}")
            yield "出错了，请稍后在试一下吧"

    return StreamingResponse(_token_gen(), media_type="text/plain")


@graph_app.post("/query_stream")
async def query_graph_stream(request: Request, query: str = Form(max_length=5000)):
    from handlers.qa_workflow import QAWorkflow, TokenEvent

    query = query.strip()
    customer_logger.info(f"query_stream: {query}")
    workflow = QAWorkflow(timeout=60)
    handler = workflow.run(query=query, streaming=True)
    client_id = _client_id(request)

    async def _token_gen():
        try:
            async for ev in handler.stream_events():
                if isinstance(ev, TokenEvent):
                    yield ev.token
            result = await handler
            _last_query_response.set(client_id, result.source_nodes)
        except Exception as e:
            error_logger.error(f"query_stream error: {e}")
            yield "出错了，请稍后在试一下吧"

    return StreamingResponse(_token_gen(), media_type="text/plain")


@graph_app.post("/query_sources", response_model=QuerySourcesResponse)
async def query_sources(request: Request):
    source_nodes = _last_query_response.get(_client_id(request))
    if not source_nodes:
        return JSONResponse(content={"status": "detail", "message": "please query first"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    return QuerySourcesResponse(source_nodes=[
        {
            'id': sn.node.id_,
            'text': sn.node.text,
            'score': sn.score,
            # 前端引用来源列表直接展示文件名（如"图书馆借阅规则.pdf"），
            # 检索/QA 路径的 node metadata 里由 documents_from_file 写入。
            'file_name': _source_file_name(sn),
        }
        for sn in source_nodes
    ])


@graph_app.post("/query", response_model=QueryResponse)
async def query_graph(request: Request, query: str = Form(max_length=5000)):
    from handlers.qa_workflow import QAWorkflow

    query_logger.info(f"query: {query}")
    try:
        workflow = QAWorkflow(timeout=60)
        result = await workflow.run(query=query, streaming=False)
    except Exception as e:
        error_logger.error(f"error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    client_id = _client_id(request)
    _last_query_response.set(client_id, result.source_nodes)
    for sn in format_source_nodes_list(result.source_nodes):
        query_logger.info(f"source: {sn}")
    query_logger.info(f"res: {result.response}")
    return QueryResponse(response=result.response)


@graph_app.post("/agent", response_model=QueryResponse)
async def agent(query: str = Form(max_length=5000)):
    from handlers.qa_workflow import QAWorkflow

    try:
        workflow = QAWorkflow(timeout=60)
        result = await workflow.run(query=query, streaming=False)
    except Exception as e:
        error_logger.error(f"error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    for sn in format_source_nodes_list(result.source_nodes):
        query_logger.info(f"source: {sn}")
    query_logger.info(f"res: {result.response}")
    return QueryResponse(response=result.response)


@graph_app.websocket("/query")
async def websocket_query(websocket: WebSocket):
    # WebSocket 认证：未配置 API_KEY 时拒绝连接
    api_key = os.environ.get('CUITCCA_API_KEY', '')
    if not api_key:
        await websocket.close(code=1008, reason="Server not configured for WebSocket access")
        return
    token = websocket.query_params.get("token", "")
    if not secrets.compare_digest(token, api_key):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        from handlers.qa_workflow import QAWorkflow

        while True:
            query = await websocket.receive_text()
            query = query.strip()[:5000]
            workflow = QAWorkflow(timeout=60)
            result = await workflow.run(query=query, streaming=False)
            await websocket.send_text(result.response)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        error_logger.error(f"websocket error: {e}")
        try:
            await websocket.send_text("出错了，请稍后在试一下吧")
        except Exception:  # nosec B110 — websocket already disconnected, nothing to do
            pass


@graph_app.post("/query_history")
async def graph_history(request: Request):
    history = _chat_histories.get(_client_id(request))
    if history is None:
        return JSONResponse(content={"status": "detail", "message": "No query graph available"},
                            status_code=status.HTTP_404_NOT_FOUND)
    return {"history": [{"role": str(msg.role), "content": msg.content} for msg in history]}


@graph_app.post("/query_router")
async def query_router(query: str = Form(max_length=5000)):
    from handlers.qa_workflow import QAWorkflow

    customer_logger.info(f"query_router: {query}")
    workflow = QAWorkflow(timeout=60)
    result = await workflow.run(query=query, streaming=False)
    customer_logger.info(f"res: {result.response}")
    return {"response": result.response}


# ---------------------------------------------------------------------------
# 上面 7 个既有端点（/create、/chat_stream、/query_stream、/query_sources、
# /query、/agent、websocket /query）以及 /query_history、/query_router 都已
# 经切到 handlers/qa_workflow.py 的 QAWorkflow 实现——不再有 Phase 3 时期
# "并行验证"的两套链路。handlers/graph_builder.py 里对应的
# CondenseQuestionChatEngine/RouterQueryEngine 组装代码已删除，只保留
# summary_index()。
#
# 下面这两个 /workflow_* 端点是 Phase 3 阶段新增、本次切换前就已经在用
# QAWorkflow 的验证端点，写法上和上面的既有端点基本一致，继续保留。
# ---------------------------------------------------------------------------


@graph_app.post("/workflow_query", response_model=QueryResponse)
async def workflow_query(request: Request, query: str = Form(max_length=5000)):
    from handlers.qa_workflow import QAWorkflow

    query = query.strip()
    customer_logger.info(f"workflow_query: {query}")
    workflow = QAWorkflow(timeout=60)
    try:
        result = await workflow.run(query=query, streaming=False)
    except Exception as e:
        error_logger.error(f"workflow_query error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    client_id = _client_id(request)
    _last_query_response.set(client_id, result.source_nodes)
    return QueryResponse(response=result.response)


@graph_app.post("/workflow_query_stream")
async def workflow_query_stream(request: Request, query: str = Form(max_length=5000)):
    from handlers.qa_workflow import QAWorkflow, TokenEvent

    query = query.strip()
    customer_logger.info(f"workflow_query_stream: {query}")
    workflow = QAWorkflow(timeout=60)
    handler = workflow.run(query=query, streaming=True)
    client_id = _client_id(request)

    async def _token_gen():
        try:
            async for ev in handler.stream_events():
                if isinstance(ev, TokenEvent):
                    yield ev.token
            result = await handler
            _last_query_response.set(client_id, result.source_nodes)
        except Exception as e:
            error_logger.error(f"workflow_query_stream error: {e}")
            yield "出错了，请稍后在试一下吧"

    return StreamingResponse(_token_gen(), media_type="text/plain")


# ---------------------------------------------------------------------------
# Agent 模式端点：agents/agent_workflow.py 的 FunctionAgent 编排，支持多轮
# 工具调用（先看目录、检索、发现不够换个角度再查一次），跟上面所有端点用的
# QAWorkflow（单次检索、零决策开销）是并存关系，不是替代——分工论证见
# agents/agent_workflow.py 模块 docstring。
#
# 端点名字特意叫 agent_chat*，不是 agent_query 或者别的可能撞到 /agent 的
# 名字：/agent 从上面的注释就能看到，是 QAWorkflow 的别名，占用它会破坏现有
# 测试和对外契约，新增端点必须避开。
# ---------------------------------------------------------------------------


@graph_app.post("/agent_chat", response_model=QueryResponse)
async def agent_chat(request: Request, query: str = Form(max_length=5000)):
    """非流式 Agent 问答。跟 ``/query`` 用同一个 ``QueryResponse`` 形状、同一套
    会话历史（``_chat_histories``）/来源查询（``_last_query_response`` +
    ``/query_sources``）机制——``run_agent()`` 把工具调用轨迹解析成
    ``NodeWithScore`` 列表（见 ``agents.agent_workflow.extract_source_nodes``），
    跟 ``QAWorkflowResult.source_nodes`` 同一个类型，所以 ``/query_sources``
    不用为 Agent 路径另开一套返回结构，两条路径的调用方体验保持一致。
    """
    from agents.agent_workflow import run_agent

    client_id = _client_id(request)
    history: list[ChatMessage] = list(_chat_histories.get(client_id) or [])
    query = query.strip()
    query_logger.info(f"agent_chat: {query}")
    try:
        result = await run_agent(query, chat_history=history)
    except Exception as e:
        error_logger.error(f"agent_chat error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    _last_query_response.set(client_id, result.source_nodes)
    history.append(ChatMessage(role=MessageRole.USER, content=query))
    history.append(ChatMessage(role=MessageRole.ASSISTANT, content=result.response))
    _chat_histories.set(client_id, history)
    query_logger.info(
        f"agent_chat res: {result.response} "
        f"tool_calls={len(result.tool_calls)} truncated={result.truncated}"
    )
    return QueryResponse(response=result.response)


@graph_app.post("/agent_chat_stream")
async def agent_chat_stream(request: Request, query: str = Form(max_length=5000)):
    """流式 Agent 问答。跟纯 token 流的 ``/chat_stream``/``/query_stream``/
    ``/workflow_query_stream`` 不是同一种协议——那三个端点用
    ``media_type="text/plain"``，body 就是拼起来的答案文本；这里的答案生成
    过程本身要经过不确定次数的工具调用，只吐 token 不够看到"发生了什么"，
    所以用 NDJSON（``media_type="application/x-ndjson"``，每行一个 JSON
    对象），把 token 增量和工具调用过程都作为独立事件暴露出来，事件类型见
    ``agents.agent_workflow.stream_agent_events`` 的文档。前端要按 ``type``
    字段区分处理，不能像另外三个端点那样直接把整个 body 当文本用。
    """
    from agents.agent_workflow import ToolCallTrace, extract_source_nodes, stream_agent_events

    client_id = _client_id(request)
    history: list[ChatMessage] = list(_chat_histories.get(client_id) or [])
    query = query.strip()
    query_logger.info(f"agent_chat_stream: {query}")

    async def _event_gen():
        token_parts: list[str] = []
        final_response = ""
        tool_calls: list[ToolCallTrace] = []
        errored = False
        try:
            async for event in stream_agent_events(query, chat_history=history):
                if event["type"] == "token":
                    token_parts.append(event["content"])
                elif event["type"] == "tool_result":
                    tool_calls.append(
                        ToolCallTrace(
                            tool_name=event["tool_name"],
                            tool_kwargs={},
                            output=event["output"],
                            is_error=event["is_error"],
                        )
                    )
                elif event["type"] == "done":
                    final_response = event["response"]
                elif event["type"] == "error":
                    # stream_agent_events 自己处理失败时是 yield 一个 error 事件
                    # 然后正常返回（不抛异常），所以下面那个 except 接不到。
                    # 不在这里标记的话，控制流会走到"用拼接的 token 兜底"，而
                    # 失败往往发生在一个 token 都没吐之前 -> final_response 是
                    # 空串 -> 一条 content="" 的 assistant 消息被写进会话历史。
                    # 后果是下一轮请求会把空消息发给 LLM（不少 OpenAI 兼容后端
                    # 直接拒绝），以及污染 /graph/chat_stream 的 condense 输入。
                    errored = True
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as e:
            error_logger.error(f"agent_chat_stream error: {e}")
            yield json.dumps({"type": "error", "message": "出错了，请稍后在试一下吧"}, ensure_ascii=False) + "\n"
            return

        # done 事件永远是 stream_agent_events 正常收尾时的最后一个事件；如果
        # 因为某种原因没收到（比如上游提前中断），退化用拼接的 token 兜底，
        # 不让会话历史/query_sources 完全拿不到这轮结果。
        if not final_response:
            final_response = "".join(token_parts)

        # 出错、或者最终什么都没产出时，不要往会话历史里写一条空的 assistant
        # 消息——宁可这一轮在历史里"没发生过"，也不要留下一条会让后续请求出错
        # 的脏记录。来源节点仍然照常记录：即使生成失败，已经完成的工具调用
        # 结果对用户排查"到底查到了什么"仍然有价值。
        _last_query_response.set(client_id, extract_source_nodes(tool_calls))
        if not errored and final_response.strip():
            history.append(ChatMessage(role=MessageRole.USER, content=query))
            history.append(ChatMessage(role=MessageRole.ASSISTANT, content=final_response))
            _chat_histories.set(client_id, history)

    return StreamingResponse(_event_gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# 自动路由端点：把"标准问答 vs Agent 模式"这个架构决策从用户界面上收回来，
# 由 handlers/auto_router.py 按检索置信度自动判定。学生问一句话，不需要先
# 弄懂"我这个问题算不算复杂"才能选对按钮。
#
# 不改动上面任何既有端点——/chat_stream、/agent_chat_stream 等继续保留原样
# （有测试覆盖，也是面试展示两条链路各自能力的入口），这里只是新增一个
# 统一入口，内部按需分发到 QAWorkflow 或 FunctionAgent。
# ---------------------------------------------------------------------------


@graph_app.post("/ask_stream")
async def ask_stream(request: Request, query: str = Form(max_length=5000)):
    """自动路由的统一流式问答入口。

    NDJSON（跟 ``/agent_chat_stream`` 同一套协议），事件类型：

    - ``route``：路由判定一算完立刻发出的第一个事件，``{"mode": "standard"
      |"agent"|"cache", "reason": "..."}``——前端用它展示"这次走了哪条路"。
      ``mode`` 多一个 ``cache``：语义缓存（``handlers/qa_cache.py``）命中，
      直接复用历史答案，连路由判定都没跑。
    - ``token``：答案增量文本，``{"content": "..."}``；standard/agent 两个
      分支统一用这个字段名（agent 分支本身就是这么发的，standard 分支这里
      特意把 ``QAWorkflow.TokenEvent.token`` 也包成同名字段，前端只需要
      一个解析器）。缓存命中分支同样发一个完整的 token 事件。
    - ``tool_call``/``tool_result``：只有 agent 分支会有（standard 分支走的
      ``QAWorkflow`` 没有工具调用），跟 ``/agent_chat_stream`` 语义一致，
      前端复用同一套"工具调用轨迹"展示逻辑。
    - ``done``：本轮回答结束，带最终 ``response``（agent 分支还带
      ``truncated``）。
    - ``suggestions``：``{"suggestions": [...]}``，在 ``done`` 之后单独发出。
      追问建议是答案讲完之后才生成的（见
      ``handlers.auto_router.generate_followup_suggestions`` docstring），
      失败/超时会拿到空数组，不代表这轮回答本身失败了。缓存命中分支不发
      追问建议（命中就是冲着"快"去的，不再搭一次最多 8 秒的 LLM 调用），
      直接发空数组。
    - ``error``：出错兜底，跟其余端点用同一个 ``_FALLBACK_ANSWER`` 系兜底
      文案。

    会话历史/来源记录跟 ``/agent_chat_stream`` 保持同样的处理方式：出错时
    不写空的 assistant 消息进历史（避免下一轮 condense/agent 请求带着一条
    空消息，见 ``/agent_chat_stream`` 里那段注释）。
    """
    from agents.agent_workflow import ToolCallTrace, extract_source_nodes, stream_agent_events
    from handlers.auto_router import MODE_AGENT, generate_followup_suggestions, route_query
    from handlers.qa_cache import CachedEntry
    from handlers.qa_workflow import QAWorkflow, TokenEvent

    client_id = _client_id(request)
    history: list[ChatMessage] = list(_chat_histories.get(client_id) or [])
    query = query.strip()
    query_logger.info(f"ask_stream: {query}")

    async def _event_gen():
        # 语义缓存优先：命中直接回答案，跳过路由判定/检索/LLM 生成（本地嵌入
        # 毫秒级成本，miss 也不亏）。lookup 自己保证不抛异常，这里不再包 try。
        from handlers import qa_cache

        cached: CachedEntry | None = await qa_cache.lookup(query)
        if cached is not None:
            kind_label = "人工沉淀" if cached.kind == "curated" else "历史问答"
            yield json.dumps(
                {
                    "type": "route",
                    "mode": "cache",
                    "reason": f"命中语义缓存（{kind_label}），已跳过检索与生成",
                },
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps(
                {"type": "token", "content": cached.answer}, ensure_ascii=False
            ) + "\n"
            yield json.dumps(
                {
                    "type": "done",
                    "response": cached.answer,
                    "tool_call_count": 0,
                    "truncated": False,
                },
                ensure_ascii=False,
            ) + "\n"
            yield json.dumps({"type": "suggestions", "suggestions": []}, ensure_ascii=False) + "\n"

            # 缓存条目里存的来源片段重建一个占位来源节点：命中时 /query_sources
            # 仍然有东西可显示，前端引用列表不空。
            if cached.source_text:
                source_node = NodeWithScore(
                    node=TextNode(
                        text=cached.source_text,
                        metadata={"file_name": cached.source_file or None},
                    ),
                    score=1.0,
                )
                _last_query_response.set(client_id, [source_node])
            history.append(ChatMessage(role=MessageRole.USER, content=query))
            history.append(ChatMessage(role=MessageRole.ASSISTANT, content=cached.answer))
            _chat_histories.set(client_id, history)
            return

        try:
            decision = await route_query(query, chat_history=history)
        except Exception as e:
            error_logger.error(f"ask_stream route_query error: {e}")
            yield json.dumps({"type": "error", "message": "出错了，请稍后在试一下吧"}, ensure_ascii=False) + "\n"
            return

        yield json.dumps(
            {"type": "route", "mode": decision.mode, "reason": decision.reason}, ensure_ascii=False
        ) + "\n"

        final_response = ""
        errored = False
        source_nodes: list[NodeWithScore] = []

        if decision.mode == MODE_AGENT:
            token_parts: list[str] = []
            tool_calls: list[ToolCallTrace] = []
            try:
                # agent 分支用原始 query（不是路由判定阶段压缩好的
                # decision.query_str）——理由见 handlers/auto_router.py 模块
                # docstring"agent 分支为什么不传压缩后的问题"一节。
                async for event in stream_agent_events(query, chat_history=history):
                    if event["type"] == "token":
                        token_parts.append(event["content"])
                    elif event["type"] == "tool_result":
                        tool_calls.append(
                            ToolCallTrace(
                                tool_name=event["tool_name"],
                                tool_kwargs={},
                                output=event["output"],
                                is_error=event["is_error"],
                            )
                        )
                    elif event["type"] == "done":
                        final_response = event["response"]
                    elif event["type"] == "error":
                        # 同 /agent_chat_stream：错误发生时不能让"用拼接
                        # token 兜底"的逻辑往会话历史里写一条空 assistant
                        # 消息，见下面的说明。
                        errored = True
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception as e:
                error_logger.error(f"ask_stream agent branch error: {e}")
                yield json.dumps(
                    {"type": "error", "message": "出错了，请稍后在试一下吧"}, ensure_ascii=False
                ) + "\n"
                return

            if not final_response:
                final_response = "".join(token_parts)
            source_nodes = extract_source_nodes(tool_calls)
        else:
            # standard 分支：复用 route_query 已经算好的 nodes + 压缩后的
            # query_str，不重复检索、不重复压缩问题——见
            # handlers/auto_router.py 模块 docstring"避免重复计算"一节。
            retriever = _PrefetchedNodesRetriever(decision.nodes)
            workflow = QAWorkflow(retriever=retriever, timeout=60)
            handler = workflow.run(
                query=decision.query_str,
                chat_history=history,
                streaming=True,
                skip_condense=True,
            )
            try:
                async for ev in handler.stream_events():
                    if isinstance(ev, TokenEvent):
                        yield json.dumps({"type": "token", "content": ev.token}, ensure_ascii=False) + "\n"
                result = await handler
            except Exception as e:
                error_logger.error(f"ask_stream standard branch error: {e}")
                yield json.dumps(
                    {"type": "error", "message": "出错了，请稍后在试一下吧"}, ensure_ascii=False
                ) + "\n"
                return

            final_response = result.response
            source_nodes = result.source_nodes
            yield json.dumps(
                {"type": "done", "response": final_response, "tool_call_count": 0, "truncated": False},
                ensure_ascii=False,
            ) + "\n"

        _last_query_response.set(client_id, source_nodes)
        if not errored and final_response.strip():
            history.append(ChatMessage(role=MessageRole.USER, content=query))
            history.append(ChatMessage(role=MessageRole.ASSISTANT, content=final_response))
            _chat_histories.set(client_id, history)

        # 成功回答后写入自动语义缓存（best-effort，store_auto 自己不抛异常）。
        # 下次问同样的问题直接命中，跳过检索 + LLM 生成。
        await qa_cache.store_auto(query, final_response, source_nodes)

        # 追问建议：必须在答案已经流式吐完之后才开始生成，不能拖慢用户看到
        # 答案的时间；生成函数自己已经把所有失败路径都降级成空列表，这里的
        # try/except 是双保险，防止调用方式本身出现意外（比如未来传参改动）
        # 导致这一步的异常反过来炸穿已经成功完成的主回答。
        try:
            suggestions = await generate_followup_suggestions(decision.query_str, source_nodes)
        except Exception:
            error_logger.error("ask_stream: 生成追问建议异常，降级为空列表", exc_info=True)
            suggestions = []
        yield json.dumps({"type": "suggestions", "suggestions": suggestions}, ensure_ascii=False) + "\n"

    return StreamingResponse(_event_gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# 反馈闭环：把"用户对回答的评价"接回知识库。这是生产级知识库平台（Dify 的
# annotation reply 等）都有的"最后一公里"——回答质量不能靠开发自己猜，用户
# 👍/👎 的每一下都在告诉系统哪条问答值得沉淀、哪条该删掉。缓存操作全部
# best-effort（handlers/qa_cache.py 不抛异常），反馈落库失败也不影响主流程。
# ---------------------------------------------------------------------------


@graph_app.post("/qa_feedback")
async def qa_feedback(
    request: Request,
    query: str = Form(max_length=5000),
    response: str = Form(max_length=20000),
    vote: str = Form(...),
):
    """回答质量反馈——反馈闭环的入口。

    - ``vote=up``（👍）：把这条问答**沉淀**进语义缓存（``kind=curated``），
      后续相似问题（同义改写级别，阈值 0.82）直接复用这份人工背过书的答案，
      跳过检索 + LLM 生成。
    - ``vote=down``（👎）：删除该问题的缓存条目（不让坏答案继续被命中），
      并把反馈写入反馈表，管理页可见。

    前端在每条回答底部放 👍/👎 两个按钮，点击即调这里（轻量 JSON，无页面
    跳转）。

    **防投毒校验**：curated 条目会被**所有用户**以 0.82 的宽松阈值复用，所以
    这里不接受任意 response——必须等于本会话历史里最后一条 assistant 消息
    （前端发的本来就是那条回答原文，校验不增加任何合法路径的成本）。历史被
    清空/过期、或者传入的是编造的问答对时直接 400，不会把垃圾写进共享缓存。
    """
    from handlers import qa_cache
    from models.user import Feedback
    from utils.file import save_feedback
    from utils.security import get_client_ip

    query = query.strip()[:2000]
    response = response.strip()[:8000]
    if vote not in ("up", "down"):
        return JSONResponse(
            content={"status": "detail", "message": "vote must be 'up' or 'down'"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not query:
        return JSONResponse(
            content={"status": "detail", "message": "query is required"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 防投毒：response 必须等于本会话最后一条 assistant 消息（归一化到端点
    # 同样的 8000 字符截断再比，避免超长答案被截断后误拒）。
    history: list[ChatMessage] = list(_chat_histories.get(_client_id(request)) or [])
    last_assistant = next(
        (m.content for m in reversed(history) if m.role == MessageRole.ASSISTANT), None
    )
    if not last_assistant or last_assistant.strip()[:8000] != response:
        return JSONResponse(
            content={"status": "detail", "message": "response does not match the session's last answer"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    source_nodes: list[NodeWithScore] = list(_last_query_response.get(_client_id(request)) or [])
    if vote == "up":
        await qa_cache.store_curated(query, response, source_nodes)
    else:
        await qa_cache.delete_by_question(query)

    # 反馈进反馈表（管理页 /manage/feedback 可见），复用既有 Feedback 模型与
    # 落库函数，不给反馈体系另开一条存储。
    try:
        feedback = Feedback(
            message=f"[{('👍 沉淀' if vote == 'up' else '👎 差评')}] Q: {query}\nA: {response}"
        )
        await save_feedback(get_client_ip(request), feedback)
    except Exception:
        error_logger.error("qa_feedback: 反馈落库失败（不影响缓存操作）", exc_info=True)

    return {"status": "ok", "vote": vote}


@graph_app.post("/cache_stats")
async def cache_stats():
    """语义缓存统计：总量 + auto/curated 分类计数。演示/运维时一眼看到"沉淀
    了多少人工问答、缓存了多大规模"。"""
    from handlers import qa_cache

    return await qa_cache.stats()
