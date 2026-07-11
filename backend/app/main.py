import asyncio
import json
import os
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from configs.llm_predictor import init_settings
from configs.load_env import (
    COOKIE_MAX_AGE,
    COOKIE_SECURE,
    LOAD_PATH,
    SAVE_PATH,
    access_stats_path,
    chroma_db_path,
    reload_env_variables,
)
from dependencies import access_stats
from dependencies.manage import access_stats as _mgmt_access_stats
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from handlers.index_crud import loadAllIndexes
from router import graph_app, index_app, manage_app, response_app
from starlette.middleware.cors import CORSMiddleware


def _get_client_ip(request) -> str:
    """安全获取客户端 IP，仅信任直接连接的 client.host"""
    return request.client.host if request.client else "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    reload_env_variables()
    init_settings()
    await loadAllIndexes()
    for directory in [SAVE_PATH, LOAD_PATH, chroma_db_path]:
        if not os.path.exists(directory):
            os.makedirs(directory)

    try:
        with open(access_stats_path) as file:
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
RATE_LIMIT_STORE_MAX = 10000
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()


async def check_rate_limit(client_ip: str) -> None:
    """检查客户端 IP 是否超过速率限制"""
    now = time.time()
    async with _rate_limit_lock:
        timestamps = _rate_limit_store[client_ip]
        while timestamps and timestamps[0] < now - RATE_LIMIT_WINDOW:
            timestamps.pop(0)
        if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请 {RATE_LIMIT_WINDOW} 秒后重试",
            )
        timestamps.append(now)
        # 清理过期 IP 条目防止内存泄漏
        if len(_rate_limit_store) > RATE_LIMIT_STORE_MAX:
            expired = [k for k, v in _rate_limit_store.items() if not v or v[0] < now - RATE_LIMIT_WINDOW]
            for k in expired:
                _rate_limit_store.pop(k, None)


@app.middleware("http")
async def session_and_stats_middleware(request, call_next):
    is_static = request.url.path.startswith("/web")
    client_ip = _get_client_ip(request)

    session_id = request.cookies.get("session_id")
    has_session = bool(session_id)
    if not has_session:
        session_id = str(uuid.uuid4())
    request.state.session_id = session_id

    # 速率限制检查（仅对 LLM 查询端点）
    if not is_static and request.url.path in (
        "/graph/query", "/graph/query_stream",
        "/graph/chat_stream", "/graph/agent",
    ):
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


# CORS origins 从环境变量读取，默认为 localhost
_cors_env = os.environ.get("CORS_ORIGINS", "")
if _cors_env:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
else:
    _cors_origins = ["http://localhost", "http://localhost:8000", "http://127.0.0.1", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'frontend')
if os.path.isdir(frontend_dir):
    app.mount("/web", StaticFiles(directory=frontend_dir, html=True), name="web")


@app.get("/")
def read_root():
    return {"Hello": "CUITCCA"}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run('main:app', host=host, port=port, reload=False)
