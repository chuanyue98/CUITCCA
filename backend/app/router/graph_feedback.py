"""反馈闭环：把"用户对回答的评价"接回知识库。这是生产级知识库平台（Dify 的
annotation reply 等）都有的"最后一公里"——回答质量不能靠开发自己猜，用户
👍/👎 的每一下都在告诉系统哪条问答值得沉淀、哪条该删掉。缓存操作全部
best-effort（handlers/qa_cache.py 不抛异常），反馈落库失败也不影响主流程。
"""
from fastapi import APIRouter, Form, Request
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.schema import NodeWithScore
from router.graph_session import _chat_histories, _client_id, _last_query_response
from starlette import status
from starlette.responses import JSONResponse
from utils.logger import error_logger

feedback_app = APIRouter()


@feedback_app.post("/qa_feedback")
async def qa_feedback(
    request: Request,
    query: str = Form(max_length=5000),
    response: str = Form(max_length=20000),
    vote: str = Form(...),
):
    """回答质量反馈——反馈闭环的入口。

    - ``vote=up``（👍）：把这条问答**沉淀**进语义缓存（``kind=curated``），
      后续相似问题（同义改写级别，阈值 0.82）直接复用这份人工背过书的答案，
      跳过检索 + LLM 生成。
    - ``vote=down``（👎）：删除该问题的缓存条目（不让坏答案继续被命中），
      并把反馈写入反馈表，管理页可见。

    前端在每条回答底部放 👍/👎 两个按钮，点击即调这里（轻量 JSON，无页面
    跳转）。

    **防投毒校验**：curated 条目会被**所有用户**以 0.82 的宽松阈值复用，所以
    这里不接受任意 response——必须等于本会话历史里最后一条 assistant 消息
    （前端发的本来就是那条回答原文，校验不增加任何合法路径的成本）。历史被
    清空/过期、或者传入的是编造的问答对时直接 400，不会把垃圾写进共享缓存。
    """
    from handlers import qa_cache
    from models.user import Feedback
    from utils.file import save_feedback
    from utils.security import get_client_ip

    query = query.strip()[:2000]
    response = response.strip()[:8000]
    if vote not in ("up", "down"):
        return JSONResponse(
            content={"status": "detail", "message": "vote must be 'up' or 'down'"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not query:
        return JSONResponse(
            content={"status": "detail", "message": "query is required"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 防投毒：response 必须等于本会话最后一条 assistant 消息（归一化到端点
    # 同样的 8000 字符截断再比，避免超长答案被截断后误拒）。
    history: list[ChatMessage] = list(_chat_histories.get(_client_id(request)) or [])
    last_assistant = next(
        (m.content for m in reversed(history) if m.role == MessageRole.ASSISTANT), None
    )
    if not last_assistant or last_assistant.strip()[:8000] != response:
        return JSONResponse(
            content={"status": "detail", "message": "response does not match the session's last answer"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    source_nodes: list[NodeWithScore] = list(_last_query_response.get(_client_id(request)) or [])
    if vote == "up":
        await qa_cache.store_curated(query, response, source_nodes)
    else:
        await qa_cache.delete_by_question(query)

    # 反馈进反馈表（管理页 /manage/feedback 可见），复用既有 Feedback 模型与
    # 落库函数，不给反馈体系另开一条存储。
    try:
        feedback = Feedback(
            message=f"[{('👍 沉淀' if vote == 'up' else '👎 差评')}] Q: {query}\nA: {response}"
        )
        await save_feedback(get_client_ip(request), feedback)
    except Exception:
        error_logger.error("qa_feedback: 反馈落库失败（不影响缓存操作）", exc_info=True)

    return {"status": "ok", "vote": vote}


@feedback_app.post("/cache_stats")
async def cache_stats():
    """语义缓存统计：总量 + auto/curated 分类计数。演示/运维时一眼看到"沉淀
    了多少人工问答、缓存了多大规模"。"""
    from handlers import qa_cache

    return await qa_cache.stats()
