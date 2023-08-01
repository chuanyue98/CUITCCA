from fastapi import APIRouter, Form
from starlette import status
from starlette.responses import JSONResponse

from handlers.handler import compose_indices_to_graph, get_history_msg

graph_app = APIRouter()

graph = None


@graph_app.post("/create")
async def create_graph():
    """创建graph"""
    global graph
    graph = compose_indices_to_graph()
    return {"status": "ok"}


@graph_app.post("/query")
async def query_graph(query: str = Form()):
    global graph
    if graph is None:
        graph = compose_indices_to_graph()
    return await graph.achat(query)


@graph_app.post("/query_history")
async def query_graph():
    global graph
    if graph is None:
        return JSONResponse(content={"status": "detail", "message": "No query graph available"},
                            status_code=status.HTTP_404_NOT_FOUND)
    return get_history_msg(graph)
