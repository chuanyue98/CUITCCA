import asyncio
import time

from fastapi import APIRouter, Form, WebSocket
from llama_index.chat_engine.types import BaseChatEngine
from llama_index.query_engine import RouterQueryEngine
from llama_index.response.schema import StreamingResponse
from llama_index.selectors.pydantic_selectors import PydanticMultiSelector
from starlette import status
from starlette.responses import JSONResponse,StreamingResponse
from starlette.websockets import WebSocketDisconnect

from exceptions.llama_exception import id_not_found_exceptions
from handlers.llama_handler import compose_graph_chat_egine, get_history_msg, indexes, compose_graph_query_engine, \
    format_source_nodes_list
from utils.llama import generate_query_engine_tools
from utils.logger import customer_logger, query_logger, error_logger

graph_app = APIRouter()

graph_chat_engine: BaseChatEngine = None
res = None


class GraphQueryEngine:
    def __init__(self):
        self.query_engine = compose_graph_query_engine()


    async def aquery(self, query_string):
        await self.query_engine.aquery(query_string)

    def reset(self):
        self.query_engine = compose_graph_query_engine()


# graph_query_engine = GraphQueryEngine().query_engine


@graph_app.post("/create")
async def create_graph():
    """创建graph"""
    global graph_chat_engine
    graph_chat_engine = compose_graph_chat_egine()
    return {"status": "ok"}


@graph_app.post("/chat_stream")
async def chaty_graph_stream(query: str = Form()):
    """
    流式的查询，返回的是一个stream
    """
    global graph_chat_engine, res
    if graph_chat_engine is None:
        graph_chat_engine = compose_graph_chat_egine()
    graph_chat_engine.reset()
    query = query.strip()
    customer_logger.info(f"chat_stream: {query}")
    res = await graph_chat_engine.astream_chat(query)
    customer_logger.info(f"res: {res}")
    return StreamingResponse(res.response_gen, media_type="text/plain")


@graph_app.post("/query_stream")
async def query_graph_stream(query: str = Form()):
    """
    流式的查询，返回的是一个stream
    """
    query_engine = compose_graph_query_engine()
    query = query.strip()
    customer_logger.info(f"query_stream: {query}")
    response = await query_engine.aquery(query)
    customer_logger.info(f"res: {response.get_formatted_sources()}")
    return StreamingResponse(response.response_gen, media_type="text/plain")


@graph_app.post("/query_sources")
async def query_sources():
    """返回的源为上一次query_stream所产生的"""
    global res
    if res is None:
        return JSONResponse(content={"status": "detail", "message": "please query first"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    customer_logger.info(res.sources)
    return res.source_nodes


@graph_app.post("/query")
@id_not_found_exceptions
async def query_graph(query: str = Form()):
    query_logger.info(f"query: {query}")
    try:
        graph_query_engine = compose_graph_query_engine()
        response = await graph_query_engine.aquery(query)
    except Exception as e:
        error_logger.error(f"error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"})
    for sn in format_source_nodes_list(response.source_nodes):
        query_logger.info(f"source: {sn}")
    query_logger.info(f"res: {response}")
    return response.response


@graph_app.websocket("/query")
async def query_graph_ws(websocket: WebSocket):
    _graph_chat_engine = compose_graph_query_engine()
    await websocket.accept()
    try:
        while True:
            query = await websocket.receive_text()
            if query == 'q':
                await websocket.close()
            customer_logger.info(f"query: {query}")
            response = await _graph_chat_engine.aquery(query)

            async def async_generator_wrapper(sync_gen):
                for value in sync_gen:
                    yield value

            async for token in async_generator_wrapper(response.response_gen):
                await websocket.send_text(token)
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        await websocket.close()


@graph_app.post("/query_history")
async def query_graph():
    """
    获取历史记录
    """
    global graph
    if graph is None:
        return JSONResponse(content={"status": "detail", "message": "No query graph available"},
                            status_code=status.HTTP_404_NOT_FOUND)
    return get_history_msg(graph)


@graph_app.post("/query_router")
async def query_router(query: str = Form()):
    query_engine_tools = generate_query_engine_tools(indexes)
    query_engine = RouterQueryEngine(
        selector=PydanticMultiSelector.from_defaults(),
        query_engine_tools=query_engine_tools,
    )
    customer_logger.info(f"query_router: {query}")
    response = query_engine.query(query)
    customer_logger.info(f"res: {response}")
    return StreamingResponse(response.response_gen, media_type="text/plain")


if __name__ == '__main__':
    pass
