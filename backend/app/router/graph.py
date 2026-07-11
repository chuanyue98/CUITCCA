import os
import secrets
import time
from collections import OrderedDict

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from handlers.graph_builder import (
    compose_graph_chat_egine,
    compose_graph_query_engine,
    get_history_msg,
    invalidate_query_engine_cache,
)
from handlers.index_crud import format_source_nodes_list
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


_graph_chat_engines: TTLCache = TTLCache()
_last_query_response: TTLCache = TTLCache()


@graph_app.post("/create")
async def create_graph(request: Request):
    client_id = _client_id(request)
    _graph_chat_engines.set(client_id, compose_graph_chat_egine())
    return {"status": "ok"}


@graph_app.post("/chat_stream")
async def chat_graph_stream(request: Request, query: str = Form(max_length=5000)):
    client_id = _client_id(request)
    chat_engine = _graph_chat_engines.get(client_id)
    if chat_engine is None:
        chat_engine = compose_graph_chat_egine()
        _graph_chat_engines.set(client_id, chat_engine)
    query = query.strip()
    customer_logger.info(f"chat_stream: {query}")
    res = await chat_engine.astream_chat(query)
    customer_logger.info(f"res: {res}")
    return StreamingResponse(res.response_gen, media_type="text/plain")


@graph_app.post("/query_stream")
async def query_graph_stream(request: Request, query: str = Form(max_length=5000)):
    query_engine = compose_graph_query_engine()
    query = query.strip()
    customer_logger.info(f"query_stream: {query}")
    response = await query_engine.aquery(query)
    customer_logger.info(f"res: {response.get_formatted_sources()}")
    client_id = _client_id(request)
    _last_query_response.set(client_id, response.source_nodes)
    return StreamingResponse(response.response_gen, media_type="text/plain")


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
    query_logger.info(f"query: {query}")
    try:
        graph_query_engine = compose_graph_query_engine()
        response = await graph_query_engine.aquery(query)
    except Exception as e:
        error_logger.error(f"error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    client_id = _client_id(request)
    _last_query_response.set(client_id, response.source_nodes)
    for sn in format_source_nodes_list(response.source_nodes):
        query_logger.info(f"source: {sn}")
    query_logger.info(f"res: {response}")
    if response.response == "Empty Response":
        response.response = '我还不知道，请反馈给我吧'
    return QueryResponse(response=response.response)


@graph_app.post("/agent", response_model=QueryResponse)
async def agent(query: str = Form(max_length=5000)):
    query_engine = compose_graph_query_engine()
    try:
        response = await query_engine.aquery(query)
    except Exception as e:
        error_logger.error(f"error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    for sn in format_source_nodes_list(response.source_nodes):
        query_logger.info(f"source: {sn}")
    query_logger.info(f"res: {response}")
    return QueryResponse(response=response.response)


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
        query_engine = compose_graph_query_engine()
        while True:
            query = await websocket.receive_text()
            query = query.strip()[:5000]
            response = await query_engine.aquery(query)
            ans = str(response)
            if ans == "Empty Response":
                ans = '我还不知道，请反馈给我吧'
            await websocket.send_text(ans)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        error_logger.error(f"websocket error: {e}")
        try:
            await websocket.send_text("出错了，请稍后在试一下吧")
        except Exception:
            pass


@graph_app.post("/query_history")
async def graph_history(request: Request):
    chat_engine = _graph_chat_engines.get(_client_id(request))
    if chat_engine is None:
        return JSONResponse(content={"status": "detail", "message": "No query graph available"},
                            status_code=status.HTTP_404_NOT_FOUND)
    history = get_history_msg(chat_engine)
    return {"history": [{"role": str(msg.role), "content": msg.content} for msg in history]}


@graph_app.post("/query_router")
async def query_router(query: str = Form(max_length=5000)):
    from handlers.graph_builder import MultiIndexQueryEngine
    query_engine = MultiIndexQueryEngine(indexes_snapshot=list(indexes))
    customer_logger.info(f"query_router: {query}")
    response = await query_engine.aquery(query)
    customer_logger.info(f"res: {response}")
    return {"response": str(response)}
