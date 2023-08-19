from fastapi import APIRouter, Form
from starlette import status
from starlette.responses import JSONResponse

from dependencies import role_required
from handlers.llama_handler import compose_indices_to_graph, get_history_msg

graph_app = APIRouter(default=role_required(allowed_roles=["admin"]))

graph = None
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
    global graph,res
    if graph is None:
        graph = compose_indices_to_graph()
    res = await graph.astream_chat(query)
    return res.response_gen

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
    global graph,res
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
