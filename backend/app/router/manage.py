import pickle
from collections import defaultdict
from dotenv import dotenv_values, set_key
from fastapi import Depends, HTTPException, status, APIRouter, Form
from starlette.requests import Request

from configs.load_env import access_stats_path, reload_env_variables
from dependencies.manage import access_stats
from models.user import Feedback
from utils.file import save_feedback_to_file

manage_app = APIRouter()


@manage_app.on_event("startup")
async def startup():
    """加载access_stats"""
    try:
        with open(access_stats_path, "rb") as file:
            access_stats_dict = pickle.load(file)

            # 将普通字典转换为defaultdict
            access_stats["total_visits"] = access_stats_dict["total_visits"]
            access_stats["user_visits"] = defaultdict(int, access_stats_dict["user_visits"])
            access_stats["endpoint_visits"] = defaultdict(int, access_stats_dict["endpoint_visits"])
    except FileNotFoundError:
        pass

        # 初始化 IP 数量
    access_stats["ip_count"] = len(access_stats["user_visits"])


@manage_app.on_event("shutdown")
def save_access_stats():
    """保存access_stats"""
    # 将defaultdict转换为普通字典
    access_stats_dict = {
        "total_visits": access_stats["total_visits"],
        "user_visits": dict(access_stats["user_visits"]),
        "endpoint_visits": dict(access_stats["endpoint_visits"])
    }

    with open(access_stats_path, "wb") as file:
        pickle.dump(access_stats_dict, file)


@manage_app.get("/stats")
async def get_stats():
    """
    获取访问统计
    """
    return access_stats


@manage_app.post("/feedback")
def create_feedback(feedback: Feedback, request: Request):
    """
    创建反馈
    """
    # 获取客户端的IP地址
    client_ip = request.client.host

    # 将问题反馈数据保存到本地文件
    save_feedback_to_file(feedback, client_ip)

    return {"message": "Feedback received"}


@manage_app.post('/env')
def set_env(openai_api_key=Form(), openai_base_url=Form(default='https://api.openai.com/v1')):
    # 读取当前的.env文件内容
    env_values = dotenv_values("../.env")
    # 更新指定的键值对
    env_values['OPENAI_API_KEY'] = openai_api_key
    env_values['OPENAI_API_BASE'] = openai_base_url

    # 将更新后的键值对写回到.env文件
    for k, v in env_values.items():
        set_key("../.env", k, v)
    reload_env_variables()
    return {"message": "环境变量已更新"}

