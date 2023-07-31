
from fastapi import FastAPI

from router import response_app,index_app

app = FastAPI()

app.include_router(index_app, prefix='/index', tags=['index'])
app.include_router(response_app, prefix='/response', tags=['response'])


@app.get("/")
def read_root():
    return {"Hello": "CUITCCA"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=8080,reload=True)
