import json
import os
from collections import defaultdict
from dotenv import dotenv_values, set_key
from fastapi import Depends, HTTPException, status, APIRouter, Form
from starlette.requests import Request

from configs.load_env import access_stats_path, reload_env_variables, PROJECT_ROOT
from dependencies.manage import access_stats
from models.user import Feedback
from utils.file import save_feedback_to_file

manage_app = APIRouter()


@manage_app.on_event("startup")
async def startup():
    """加载access_stats"""
    try:
        with open(access_stats_path, "r") as file:
            access_stats_dict = json.load(file)
            access_stats["total_visits"] = access_stats_dict["total_visits"]
            access_stats["user_visits"] = defaultdict(int, access_stats_dict["user_visits"])
            access_stats["endpoint_visits"] = defaultdict(int, access_stats_dict["endpoint_visits"])
    except FileNotFoundError:
        pass

    access_stats["ip_count"] = len(access_stats["user_visits"])


@manage_app.on_event("shutdown")
def save_access_stats():
    """保存access_stats"""
    access_stats_dict = {
        "total_visits": access_stats["total_visits"],
        "user_visits": dict(access_stats["user_visits"]),
        "endpoint_visits": dict(access_stats["endpoint_visits"])
    }

    with open(access_stats_path, "w") as file:
        json.dump(access_stats_dict, file)


@manage_app.get("/stats")
async def get_stats():
    """
    获取访问统计
    """
    return dict(access_stats)


@manage_app.post("/feedback")
def create_feedback(feedback: Feedback, request: Request):
    """
    创建反馈
    """
    client_ip = request.client.host
    save_feedback_to_file(feedback, client_ip)
    return {"message": "Feedback received"}


_env_path = os.path.join(os.path.dirname(PROJECT_ROOT), '.env')


@manage_app.post('/env')
def set_env(openai_api_key=Form(), openai_base_url=Form(default='https://api.openai.com/v1')):
    if not openai_api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is required")

    env_values = dotenv_values(_env_path)
    env_values['OPENAI_API_KEY'] = openai_api_key
    env_values['OPENAI_API_BASE'] = openai_base_url

    for k, v in env_values.items():
        set_key(_env_path, k, v)
    reload_env_variables()
    return {"message": "环境变量已更新"}
