from contextlib import asynccontextmanager
import json
import os
import threading
import uuid
from collections import defaultdict
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from dependencies import access_stats
from dependencies.manage import access_stats as _mgmt_access_stats
from configs.llm_predictor import init_settings
from handlers.llama_handler import loadAllIndexes
from configs.load_env import index_save_directory, SAVE_PATH, LOAD_PATH, access_stats_path
from router import response_app, index_app, graph_app, manage_app, test_app
from utils.security import ApiKeyMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_settings()
    loadAllIndexes()
    for directory in [index_save_directory, SAVE_PATH, LOAD_PATH]:
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
app.include_router(test_app, prefix='/test', tags=['test'])

access_stats_lock = threading.Lock()


@app.middleware("http")
async def session_and_stats_middleware(request, call_next):
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    safe_ip = client_ip.replace(":", "_").replace(".", "_")
    cookie_name = f"session_id_{safe_ip}"
    session_id = request.cookies.get(cookie_name)
    has_session = bool(session_id)
    if not has_session:
        session_id = str(uuid.uuid4())
        request.state.session_id = session_id
    else:
        request.state.session_id = session_id

    with access_stats_lock:
        access_stats["total_visits"] += 1
        access_stats["user_visits"][client_ip] += 1
        access_stats["endpoint_visits"][request.url.path] += 1
        access_stats["ip_count"] = len(access_stats["user_visits"])

    response = await call_next(request)
    if not has_session:
        response.set_cookie(key=cookie_name, value=session_id, path="/", httponly=True, samesite="lax")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


API_KEY = os.environ.get('CUITCCA_API_KEY', '')

if API_KEY:
    app.add_middleware(ApiKeyMiddleware, api_key=API_KEY)


frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'frontend')
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/web", StaticFiles(directory=frontend_dir, html=True), name="web")


@app.get("/")
def read_root():
    return {"Hello": "CUITCCA"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=8000, reload=False)
