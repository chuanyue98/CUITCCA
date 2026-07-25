import asyncio
import os

from configs.load_env import PROJECT_ROOT
from dependencies.manage import access_stats, access_stats_lock
from dotenv import dotenv_values
from fastapi import APIRouter, Depends
from models.response import FeedbackListResponse, FeedbackResponse, StatsResponse
from models.user import Feedback
from starlette.requests import Request
from utils.file import save_feedback
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


@manage_app.get('/env', dependencies=[Depends(require_configured_api_key)])
async def get_env():
    """只读脱敏返回当前环境变量配置，不再支持通过接口修改。

    修改 LLM 配置请直接编辑 .env 文件后重启服务。原来通过 POST /env
    在线修改的能力存在安全风险（接口可改 LLM 后端和密钥），已移除。
    """
    env_values = dotenv_values(_env_path)

    def _mask(value):
        if not value:
            return ''
        if len(value) <= 4:
            return '****'
        return '****' + value[-4:]

    masked_file = {
        'OPENAI_API_KEY': _mask(env_values.get('OPENAI_API_KEY', '')),
        'OPENAI_API_BASE': env_values.get('OPENAI_API_BASE', ''),
        'OPENAI_API_MODEL': env_values.get('OPENAI_API_MODEL', ''),
    }
    runtime = {
        'OPENAI_API_KEY': _mask(os.environ.get('OPENAI_API_KEY', '')),
        'OPENAI_API_BASE': os.environ.get('OPENAI_API_BASE', ''),
        'OPENAI_API_MODEL': os.environ.get('OPENAI_API_MODEL', ''),
    }
    return {'status': 'ok', 'env_file': masked_file, 'runtime': runtime}
