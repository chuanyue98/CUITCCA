import asyncio
from contextlib import asynccontextmanager
import json
import os
import time
import uuid
from collections import defaultdict
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from dependencies import access_stats
from dependencies.manage import access_stats as _mgmt_access_stats
from configs.llm_predictor import init_settings
from handlers.index_crud import loadAllIndexes
from configs.load_env import chroma_db_path, SAVE_PATH, LOAD_PATH, access_stats_path, reload_env_variables, COOKIE_SECURE, COOKIE_MAX_AGE
from router import response_app, index_app, graph_app, manage_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    reload_env_variables()
    init_settings()
    await loadAllIndexes()
    for directory in [SAVE_PATH, LOAD_PATH, chroma_db_path]:
        if not os.path.exists(directory):
            os.makedirs(directory)

    try:
        with open(access_stats_path, "r") as file:
            access_stats_dict = json.load(file)
            _mgmt_access_stats["total_visits"] = access_stats_dict["total_visits"]
            _mgmt_access_stats["user_visits"] = defaultdict(int, access_stats_dict["user_visits"])
            _mgmt_access_stats["endpoint_visits"] = defaultdict(int, access_stats_dict["endpoint_visits"])
    except FileNotFoundError:
        pass
    _mgmt_access_stats["ip_count"] = len(_mgmt_access_stats["user_visits"])

    yield

    access_stats_dict = {
        "total_visits": _mgmt_access_stats["total_visits"],
        "user_visits": dict(_mgmt_access_stats["user_visits"]),
        "endpoint_visits": dict(_mgmt_access_stats["endpoint_visits"]),
    }
    with open(access_stats_path, "w") as file:
        json.dump(access_stats_dict, file)


app = FastAPI(lifespan=lifespan)

app.include_router(index_app, prefix='/index', tags=['index'])
app.include_router(graph_app, prefix='/graph', tags=['graph'])
app.include_router(response_app, prefix='/response', tags=['response'])
app.include_router(manage_app, prefix='/manage', tags=['manage'])

access_stats_lock = asyncio.Lock()

# 速率限制：每 IP 每 60 秒最多 30 次请求（LLM 查询端点）
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 30
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()


async def check_rate_limit(client_ip: str) -> None:
    """检查客户端 IP 是否超过速率限制"""
    now = time.time()
    async with _rate_limit_lock:
        timestamps = _rate_limit_store[client_ip]
        # 清理过期记录
        while timestamps and timestamps[0] < now - RATE_LIMIT_WINDOW:
            timestamps.pop(0)
        if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请 {RATE_LIMIT_WINDOW} 秒后重试",
            )
        timestamps.append(now)


@app.middleware("http")
async def session_and_stats_middleware(request, call_next):
    # 静态文件请求不统计、不设 Cookie
    is_static = request.url.path.startswith("/web")
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")

    # 使用统一的 session_id cookie，不再暴露客户端 IP
    session_id = request.cookies.get("session_id")
    has_session = bool(session_id)
    if not has_session:
        session_id = str(uuid.uuid4())
    request.state.session_id = session_id

    # 速率限制检查（仅对 LLM 查询端点）
    if not is_static and request.url.path in ("/graph/query", "/graph/query_stream", "/graph/chat_stream", "/graph/agent"):
        try:
            await check_rate_limit(client_ip)
        except HTTPException:
            return JSONResponse(
                content={"detail": "请求过于频繁，请稍后重试"},
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    # 统计（排除静态文件）
    if not is_static:
        async with access_stats_lock:
            access_stats["total_visits"] += 1
            access_stats["user_visits"][client_ip] += 1
            access_stats["endpoint_visits"][request.url.path] += 1
            access_stats["ip_count"] = len(access_stats["user_visits"])

    response = await call_next(request)
    if not has_session and not is_static:
        response.set_cookie(
            key="session_id",
            value=session_id,
            path="/",
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
            max_age=COOKIE_MAX_AGE,
        )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:8000", "http://127.0.0.1", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'frontend')
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/web", StaticFiles(directory=frontend_dir, html=True), name="web")


@app.get("/")
def read_root():
    return {"Hello": "CUITCCA"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=8000, reload=False)
