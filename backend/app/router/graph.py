import os
import secrets
import time
from collections import OrderedDict

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from handlers.index_crud import format_source_nodes_list
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from models.response import QueryResponse, QuerySourcesResponse
from starlette import status
from starlette.responses import JSONResponse, StreamingResponse
from utils.logger import customer_logger, error_logger, query_logger

graph_app = APIRouter()

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
