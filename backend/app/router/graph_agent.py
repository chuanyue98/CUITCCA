"""Agent 模式端点：agents/agent_workflow.py 的 FunctionAgent 编排，支持多轮
工具调用（先看目录、检索、发现不够换个角度再查一次），跟 graph_qa.py 所有
端点用的 QAWorkflow（单次检索、零决策开销）是并存关系，不是替代——分工论证
见 agents/agent_workflow.py 模块 docstring。

端点名字特意叫 agent_chat*，不是 agent_query 或者别的可能撞到 /agent 的
名字：/agent 是 QAWorkflow 的别名（graph_qa.py），占用它会破坏现有测试和
对外契约，新增端点必须避开。
"""
import json

from fastapi import APIRouter, Form, Request
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from models.response import QueryResponse
from router.graph_session import _chat_histories, _client_id, _last_query_response
from starlette import status
from starlette.responses import JSONResponse, StreamingResponse
from utils.logger import error_logger, query_logger

agent_app = APIRouter()


@agent_app.post("/agent_chat", response_model=QueryResponse)
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


@agent_app.post("/agent_chat_stream")
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
