from typing import List

from fastapi import APIRouter, Form
from llama_index import ComposableGraph
from llama_index.chat_engine.types import BaseChatEngine
from llama_index.indices.base import BaseIndex
from llama_index.query_engine import RouterQueryEngine
from llama_index.selectors.pydantic_selectors import PydanticMultiSelector
from llama_index.tools import QueryEngineTool
from starlette import status
from starlette.responses import JSONResponse, StreamingResponse

from configs.config import Prompts
from dependencies import role_required
from handlers.llama_handler import compose_indices_to_graph, get_history_msg, indexes, compose_graph_query_egine
from utils.logger import customer_logger

graph_app = APIRouter(default=role_required(allowed_roles=["admin"]))

graph: BaseChatEngine
res = None


@graph_app.post("/create")
async def create_graph():
    """创建graph"""
    global graph
    graph = compose_indices_to_graph()
    return {"status": "ok"}


@graph_app.post("/query_stream")
async def query_graph_stream(query: str = Form()):
    """
    流式的查询，返回的是一个stream
    """
    global graph, res
    if graph is None:
        graph = compose_indices_to_graph()
    graph.reset()
    query = query.strip()
    res = await graph.astream_chat(query)
    customer_logger.info(f"query_stream: {query}")
    return StreamingResponse(res.response_gen, media_type="text/plain")



@graph_app.post("/query_sources")
async def query_sources():
    """返回的源为上一次query_stream所产生的"""
    global res
    if res is None:
        return JSONResponse(content={"status": "detail", "message": "please query first"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    return res.source_nodes


@graph_app.post("/query")
async def query_graph(query: str = Form()):
    global graph, res
    if graph is None:
        graph = compose_indices_to_graph()
    res = await graph.achat(query)
    return res.response


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
    res = query_engine.query(query)
    return StreamingResponse(res.response_gen, media_type="text/plain")


def generate_query_engine_tools(indexes: List[BaseIndex]) -> List[QueryEngineTool]:
    query_engine_tools = []
    for index in indexes:
        query_engine = index.as_query_engine(streaming=True,
                                             text_qa_template=Prompts.QA_PROMPT.value,
                                             refine_template=Prompts.REFINE_PROMPT.value)
        description = index.summary
        tool = QueryEngineTool.from_defaults(query_engine=query_engine, description=description)
        query_engine_tools.append(tool)

    return query_engine_tools
