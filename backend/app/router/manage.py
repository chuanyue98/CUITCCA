import asyncio
import os

from configs.llm_predictor import build_llm
from configs.load_env import PROJECT_ROOT, reload_env_variables
from dependencies.manage import access_stats, access_stats_lock
from dotenv import dotenv_values, set_key
from fastapi import APIRouter, Depends, Form, HTTPException
from llama_index.core import Settings
from models.response import EnvUpdateResponse, FeedbackListResponse, FeedbackResponse, StatsResponse
from models.user import Feedback
from starlette.requests import Request
from utils.file import save_feedback
from utils.logger import audit_logger
from utils.security import get_client_ip, require_configured_api_key

manage_app = APIRouter()


@manage_app.get("/stats", response_model=StatsResponse, dependencies=[Depends(require_configured_api_key)])
async def get_stats():
    """获取访问统计"""
    async with access_stats_lock:
        return StatsResponse(
            total_visits=access_stats["total_visits"],
            ip_count=access_stats["ip_count"],
            user_visits=dict(access_stats["user_visits"]),
            endpoint_visits=dict(access_stats["endpoint_visits"]),
        )


@manage_app.post("/feedback", response_model=FeedbackResponse, dependencies=[Depends(require_configured_api_key)])
async def create_feedback(feedback: Feedback, request: Request):
    """创建反馈"""
    client_ip = get_client_ip(request)
    await save_feedback(client_ip, feedback)
    return FeedbackResponse(message="Feedback received")


@manage_app.get("/feedback", response_model=FeedbackListResponse, dependencies=[Depends(require_configured_api_key)])
async def get_feedback(limit: int = 100):
    """列出最近的用户反馈"""
    from configs.load_env import db_path
    from utils import db
    entries = await asyncio.to_thread(db.list_feedback, db_path, limit)
    return FeedbackListResponse(feedback=entries)


_env_path = os.path.join(os.path.dirname(PROJECT_ROOT), '.env')


@manage_app.post('/env', response_model=EnvUpdateResponse, dependencies=[Depends(require_configured_api_key)])
async def set_env(
    request: Request,
    openai_api_key: str = Form(max_length=200),
    openai_base_url: str = Form(
        default='https://api.openai.com/v1', max_length=500
    ),
):
    if not openai_api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is required")

    # 审计日志：记录 LLM 后端变更
    client_ip = get_client_ip(request)
    audit_logger.info(
        f"AUDIT: LLM backend changed by {client_ip} | "
        f"base_url={openai_base_url} | key=***{openai_api_key[-4:] if len(openai_api_key) >= 4 else '****'}"
    )

    # 阻塞的磁盘 I/O 放到线程池中执行，配置重载和 Settings 修改留在主线程
    def _do_env_update():
        env_values = dotenv_values(_env_path)
        env_values['OPENAI_API_KEY'] = openai_api_key
        env_values['OPENAI_API_BASE'] = openai_base_url
        for k, v in env_values.items():
            if v is not None:
                set_key(_env_path, k, v)

    await asyncio.to_thread(_do_env_update)
    reload_env_variables()
    Settings.llm = build_llm()
    return EnvUpdateResponse(message="环境变量已更新")
