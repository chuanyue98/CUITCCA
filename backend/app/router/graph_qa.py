"""QAWorkflow 系端点：标准问答的流式/非流式、会话历史、来源查询、WebSocket、
以及两个 Phase 3 验证期端点。按检索置信度自动路由的统一入口在 graph_ask.py，
Agent 多跳工具调用端点在 graph_agent.py——三条链路的分工论证见各自模块。
"""
import os
import secrets

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from handlers.index_crud import format_source_nodes_list
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.schema import NodeWithScore, QueryBundle
from models.response import QueryResponse, QuerySourcesResponse
from router.graph_session import _chat_histories, _client_id, _last_query_response
from starlette import status
from starlette.responses import JSONResponse, StreamingResponse
from utils.logger import customer_logger, error_logger, query_logger

qa_app = APIRouter()


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


@qa_app.post("/create")
async def create_graph(request: Request):
    client_id = _client_id(request)
    _chat_histories.set(client_id, [])
    return {"status": "ok"}


@qa_app.post("/chat_stream")
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


@qa_app.post("/query_stream")
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


@qa_app.post("/query_sources", response_model=QuerySourcesResponse)
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


@qa_app.post("/query", response_model=QueryResponse)
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


@qa_app.post("/agent", response_model=QueryResponse)
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


@qa_app.websocket("/query")
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


@qa_app.post("/query_history")
async def graph_history(request: Request):
    history = _chat_histories.get(_client_id(request))
    if history is None:
        return JSONResponse(content={"status": "detail", "message": "No query graph available"},
                            status_code=status.HTTP_404_NOT_FOUND)
    return {"history": [{"role": str(msg.role), "content": msg.content} for msg in history]}


@qa_app.post("/query_router")
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


@qa_app.post("/workflow_query", response_model=QueryResponse)
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


@qa_app.post("/workflow_query_stream")
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
