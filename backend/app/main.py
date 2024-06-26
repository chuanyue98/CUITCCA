from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from dependencies import access_stats
from router import response_app, index_app, graph_app, manage_app

app = FastAPI()

app.include_router(index_app, prefix='/index', tags=['index'])
app.include_router(graph_app, prefix='/graph', tags=['graph'])
app.include_router(response_app, prefix='/response', tags=['response'])
app.include_router(manage_app, prefix='/manage', tags=['manage'])


@app.middleware("http")
async def access_stats_middleware(request, call_next):
    client_ip = request.headers.get("X-Real-IP") or request.client.host

    # 更新总进站量
    access_stats["total_visits"] += 1

    # 更新用户访问次数和接口访问次数
    access_stats["user_visits"][client_ip] += 1
    access_stats["endpoint_visits"][request.url.path] += 1

    # 统计不同 IP 的数量
    access_stats["ip_count"] = len(access_stats["user_visits"])

    response = await call_next(request)
    return response


# 设置允许的来源（即允许跨域请求的域名）
# origins = [
#     "http://localhost",
#     "http://localhost:3000",
#     # 添加其他需要允许的域名
# ]

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"Hello": "CUITCCA"}


if __name__ == "__main__":
    import uvicorn
    # os.makedirs(ERRORLOG_PATH, exist_ok=True)
    uvicorn.run('main:app', host='127.0.0.1', port=8000, reload=False)
