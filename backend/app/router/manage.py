import pickle
from collections import defaultdict
from datetime import timedelta

from fastapi import Depends, HTTPException, status, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from starlette.requests import Request

from configs.load_env import access_stats_path, FEEDBACK_PATH
from dependencies.manage import get_current_active_user, role_required, fake_users_db, get_current_user, access_stats
from handlers.auth import authenticate_user, ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from models.user import Token, User, Feedback
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


@manage_app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@manage_app.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@manage_app.get("/users/me/items/")
@role_required(['admin'])
async def read_own_items(current_user: User = Depends(get_current_active_user)):
    return [{"item_id": "Foo", "owner": current_user.username}]
