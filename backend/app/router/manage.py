import os
from dotenv import dotenv_values, set_key
from fastapi import Depends, HTTPException, APIRouter, Form
from llama_index.core import Settings
from starlette.requests import Request

from utils.security import require_configured_api_key

from configs.load_env import PROJECT_ROOT, reload_env_variables
from configs.llm_predictor import build_llm
from dependencies.manage import access_stats
from models.user import Feedback
from models.response import StatsResponse, FeedbackResponse, EnvUpdateResponse
from utils.file import save_feedback_to_file

manage_app = APIRouter()


@manage_app.get("/stats", response_model=StatsResponse, dependencies=[Depends(require_configured_api_key)])
async def get_stats():
    """
    获取访问统计
    """
    return StatsResponse(
        total_visits=access_stats["total_visits"],
        ip_count=access_stats["ip_count"],
        user_visits=dict(access_stats["user_visits"]),
        endpoint_visits=dict(access_stats["endpoint_visits"]),
    )


@manage_app.post("/feedback", response_model=FeedbackResponse, dependencies=[Depends(require_configured_api_key)])
async def create_feedback(feedback: Feedback, request: Request):
    """
    创建反馈
    """
    client_ip = request.client.host if request.client else "unknown"
    await save_feedback_to_file(feedback, client_ip)
    return FeedbackResponse(message="Feedback received")


_env_path = os.path.join(os.path.dirname(PROJECT_ROOT), '.env')


@manage_app.post('/env', response_model=EnvUpdateResponse, dependencies=[Depends(require_configured_api_key)])
def set_env(openai_api_key=Form(), openai_base_url=Form(default='https://api.openai.com/v1')):
    if not openai_api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is required")

    env_values = dotenv_values(_env_path)
    env_values['OPENAI_API_KEY'] = openai_api_key
    env_values['OPENAI_API_BASE'] = openai_base_url

    for k, v in env_values.items():
        set_key(_env_path, k, v)
    reload_env_variables()
    Settings.llm = build_llm()
    return EnvUpdateResponse(message="环境变量已更新")
