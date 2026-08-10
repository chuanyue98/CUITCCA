import json
import os
import secrets
import time
from collections import OrderedDict

from fastapi import APIRouter, Depends, Form, Request, WebSocket, WebSocketDisconnect
from handlers.index_crud import format_source_nodes_list
from llama_index.core.base.llms.types import ChatMessage, MessageRole
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
