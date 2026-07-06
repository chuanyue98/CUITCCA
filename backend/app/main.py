import os
import threading
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from dependencies import access_stats
from router import response_app, index_app, graph_app, manage_app

app = FastAPI()

app.include_router(index_app, prefix='/index', tags=['index'])
app.include_router(graph_app, prefix='/graph', tags=['graph'])
app.include_router(response_app, prefix='/response', tags=['response'])
app.include_router(manage_app, prefix='/manage', tags=['manage'])

access_stats_lock = threading.Lock()


@app.middleware("http")
async def access_stats_middleware(request, call_next):
    client_ip = request.headers.get("X-Real-IP") or request.client.host

    with access_stats_lock:
        access_stats["total_visits"] += 1
        access_stats["user_visits"][client_ip] += 1
        access_stats["endpoint_visits"][request.url.path] += 1
        access_stats["ip_count"] = len(access_stats["user_visits"])

    response = await call_next(request)
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


API_KEY = os.environ.get('CUITCCA_API_KEY', '')


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if API_KEY:
            auth = request.headers.get('Authorization', '')
            if not auth.startswith('Bearer ') or auth.removeprefix('Bearer ') != API_KEY:
                raise HTTPException(status_code=401, detail="Unauthorized")
        return await call_next(request)


if API_KEY:
    app.add_middleware(AuthMiddleware)


frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'frontend')
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/web", StaticFiles(directory=frontend_dir, html=True), name="web")


@app.get("/")
def read_root():
    return {"Hello": "CUITCCA"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=8000, reload=False)
