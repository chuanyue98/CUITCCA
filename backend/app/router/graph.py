from fastapi import APIRouter, Form, Request
from llama_index.core.agent import ReActAgent
from llama_index.core.chat_engine.types import BaseChatEngine
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.selectors.pydantic_selectors import PydanticMultiSelector
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from starlette import status
from starlette.responses import JSONResponse, StreamingResponse

from exceptions.llama_exception import id_not_found_exceptions
from handlers.llama_handler import compose_graph_chat_egine, get_history_msg, indexes, compose_graph_query_engine, \
    format_source_nodes_list, get_index_by_name
from utils.llama import generate_query_engine_tools
from utils.logger import customer_logger, query_logger, error_logger

graph_app = APIRouter()


def _client_id(request: Request) -> str:
    return request.headers.get("X-Real-IP") or request.client.host


# 按客户端隔离，避免不同用户共享同一个对话状态/查询结果（见 code review 报告）
_graph_chat_engines: dict[str, BaseChatEngine] = {}


@graph_app.post("/create")
async def create_graph(request: Request):
    """创建graph"""
    _graph_chat_engines[_client_id(request)] = compose_graph_chat_egine()
    return {"status": "ok"}


@graph_app.post("/chat_stream")
async def chaty_graph_stream(request: Request, query: str = Form()):
    """
    流式的查询，返回的是一个stream
    """
    client_id = _client_id(request)
    chat_engine = _graph_chat_engines.get(client_id)
    if chat_engine is None:
        chat_engine = compose_graph_chat_egine()
        _graph_chat_engines[client_id] = chat_engine
    chat_engine.reset()
    query = query.strip()
    customer_logger.info(f"chat_stream: {query}")
    res = await chat_engine.astream_chat(query)
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


# 按客户端隔离，避免不同用户读到彼此的查询结果；读取时不弹出，允许重复读取
_last_query_response: dict[str, list] = {}


@graph_app.post("/query_sources")
async def query_sources(request: Request):
    """返回的源为上一次query_stream所产生的"""
    source_nodes = _last_query_response.get(_client_id(request))
    if not source_nodes:
        return JSONResponse(content={"status": "detail", "message": "please query first"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    return {"source_nodes": [
        {
            'id': sn.node.id_,
            'text': sn.node.text,
            'score': sn.score,
        }
        for sn in source_nodes
    ]}


@graph_app.post("/query")
@id_not_found_exceptions
async def query_graph(request: Request, query: str = Form()):
    query_logger.info(f"query: {query}")
    try:
        graph_query_engine = compose_graph_query_engine()
        response = await graph_query_engine.aquery(query)
    except Exception as e:
        error_logger.error(f"error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"})
    _last_query_response[_client_id(request)] = response.source_nodes
    for sn in format_source_nodes_list(response.source_nodes):
        query_logger.info(f"source: {sn}")
    query_logger.info(f"res: {response}")
    if response.response == "Empty Response":
        response.response = '我还不知道，请反馈给我吧'
    return {"response": response.response}


@graph_app.post("/agent")
@id_not_found_exceptions
async def agent(query: str = Form()):
    query_engine_tools = [
        QueryEngineTool(
            query_engine=get_index_by_name(index.index_id).as_query_engine(),
            metadata=ToolMetadata(
                name=index.index_id,
                description=index.summary,
            ),
        )
        for index in indexes
    ]
    agent = ReActAgent.from_tools(query_engine_tools, verbose=True)
    try:
        response = await agent.achat(query)
    except Exception as e:
        error_logger.error(f"error: {e}")
        return JSONResponse(content={"status": "detail", "message": "出错了，请稍后在试一下吧"})
    for sn in format_source_nodes_list(response.source_nodes):
        query_logger.info(f"source: {sn}")
    query_logger.info(f"res: {response}")
    return {"response": response.response}


@graph_app.post("/query_history")
async def graph_history(request: Request):
    """
    获取历史记录
    """
    chat_engine = _graph_chat_engines.get(_client_id(request))
    if chat_engine is None:
        return JSONResponse(content={"status": "detail", "message": "No query graph available"},
                            status_code=status.HTTP_404_NOT_FOUND)
    history = get_history_msg(chat_engine)
    return {"history": [{"role": str(msg.role), "content": msg.content} for msg in history]}


@graph_app.post("/query_router")
async def query_router(query: str = Form()):
    query_engine_tools = generate_query_engine_tools(indexes)
    query_engine = RouterQueryEngine(
        selector=PydanticMultiSelector.from_defaults(),
        query_engine_tools=query_engine_tools,
    )
    customer_logger.info(f"query_router: {query}")
    response = await query_engine.aquery(query)
    customer_logger.info(f"res: {response}")
    return {"response": str(response)}
