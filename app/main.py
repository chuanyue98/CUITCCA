
from fastapi import FastAPI, Form, UploadFile, File
from llama_index import VectorStoreIndex, Document
from starlette.responses import JSONResponse

from app.handlers.handler import loadAllIndexes, index_save_directory
from router import index_app

# from handlers import createIndex, indexes, loadAllIndexes, get_all_docs, deleteDocById, updateById, insert_into_index, \
#     saveIndex, LOAD_PATH, SAVE_PATH, index_save_directory, QA_PROMPT_TMPL, compose_indices_to_graph

app = FastAPI()

app.include_router(index_app, prefix='/index', tags=['index'])


@app.get("/")
def read_root():
    return {"Hello": "World"}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run('main:app', host='127.0.0.1', port=8080)
