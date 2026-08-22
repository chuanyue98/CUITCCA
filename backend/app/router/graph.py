"""graph 路由的组装层：鉴权依赖 + 四个按链路拆分的子路由。

- graph_qa.py        QAWorkflow 系端点（/create、/chat_stream、/query* 等）
- graph_agent.py     Agent 多跳工具调用（/agent_chat、/agent_chat_stream）
- graph_ask.py       自动路由统一入口（/ask_stream）
- graph_feedback.py  反馈闭环（/qa_feedback、/cache_stats）
- graph_session.py   上述四组端点共享的会话状态（TTLCache）

子路由各自持有 APIRouter（而不是共用本模块的 graph_app）是为了可独立导入：
tests/_router_loader.py 会把本文件按独立模块实例加载，若子模块反过来
`from router.graph import graph_app` 注册路由，standalone 实例会拿不到任何
路由（注册全落在 canonical 实例上）。

``_chat_histories`` 等会话状态从 graph_session 转出口纯粹是兼容性 re-export：
十几个测试用 ``from router.graph import _chat_histories`` 直接检查会话状态。
"""
from fastapi import APIRouter, Depends
from router.graph_agent import agent_app
from router.graph_ask import ask_app
from router.graph_feedback import feedback_app
from router.graph_qa import qa_app
from utils.security import require_api_key_if_configured

graph_app = APIRouter(dependencies=[Depends(require_api_key_if_configured)])
graph_app.include_router(qa_app)
graph_app.include_router(agent_app)
graph_app.include_router(ask_app)
graph_app.include_router(feedback_app)

# 兼容性 re-export：测试从 router.graph 取会话状态（新代码请从
# router.graph_session import）。
from router.graph_session import _chat_histories, _client_id, _last_query_response  # noqa: E402,F401
