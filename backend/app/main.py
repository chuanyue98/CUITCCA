from fastapi import FastAPI

from router import response_app, index_app, graph_app

from fastapi_amis_admin.admin.settings import Settings
from fastapi_amis_admin.admin.site import AdminSite

app = FastAPI()

# site = AdminSite(settings=Settings(database_url_async='sqlite+aiosqlite:///admisadmin.db'))
# site.mount_app(app)

app.include_router(index_app, prefix='/index', tags=['index'])
app.include_router(graph_app, prefix='/graph', tags=['graph'])
app.include_router(response_app, prefix='/response', tags=['response'])


@app.get("/")
def read_root():
    return {"Hello": "CUITCCA"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=8080,reload=True)
