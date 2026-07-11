import logging
import os
import re
import uuid
from typing import List

import aiofiles
from fastapi import APIRouter, Form, File, UploadFile, status, Depends
from llama_index.core import Document
from starlette.responses import JSONResponse

from configs.config import Prompts
from configs.load_env import SAVE_PATH, LOAD_PATH
from configs.llm_predictor import build_llm
from handlers import list_index_names, delete_collection
from handlers.graph_builder import summary_index
from handlers.index_crud import (
    _indexes_lock,
    indexes,
    createIndex,
    loadAllIndexes,
    insert_into_index,
    embeddingQA,
    get_all_docs,
    updateNodeById,
    deleteNodeById,
    deleteDocById,
    saveIndex,
    citf,
)
from utils.logger import customer_logger
from dependencies import get_index
from models.response import IndexListResponse, QueryResponse, UploadResponse
from utils.file import read_file_contents, safe_filename
from utils.llama import formatted_pairs, generate_qa_batched, extract_content_after_backslash, \
    build_qa_generation_prompt
from utils.upload import validate_upload_file, FileTooLargeError, InvalidFileTypeError

index_app = APIRouter()


def _sanitize_index_name(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)


@index_app.get("/")
async def index():
    return {"status": "ok", "load": "ok"}


@index_app.get("/list", response_model=IndexListResponse)
async def get_index_list():
    async with _indexes_lock:
        index_list = [index.index_id for index in indexes]
    return IndexListResponse(indexes=index_list)


@index_app.post("/create")
async def create_index(index_name: str = Form()):
    sanitized_name = _sanitize_index_name(index_name)
    if sanitized_name in list_index_names():
        return JSONResponse(content={'status': 'error', 'msg': 'index already exists'})
    createIndex(sanitized_name)
    await loadAllIndexes()
    return JSONResponse(content={
        'status': 'success', 
        'msg': f'index {sanitized_name} created',
        'index_name': sanitized_name
    })


@index_app.get("/{index_name}/info")
async def index_info(index=Depends(get_index)):
    docs = get_all_docs(index)
    return JSONResponse(content={'docs': docs}, status_code=status.HTTP_200_OK)


@index_app.post("/delete")
async def delete_index(index_name: str = Form()):
    sanitized_name = _sanitize_index_name(index_name)
    if sanitized_name in list_index_names():
        delete_collection(sanitized_name)
        await loadAllIndexes()
        return {"status": "deleted"}
    else:
        return JSONResponse(content={'status': 'detail', 'message': 'index not exist'},
                            status_code=status.HTTP_404_NOT_FOUND)


@index_app.post("/{index_name}/query", response_model=QueryResponse)
async def query_index(index=Depends(get_index), query: str = Form()):
    customer_logger.info(f"query index {index.index_id} with query {query}")

    engine = index.as_query_engine(
        text_qa_template=Prompts.QA_PROMPT.value.template,
        refine_template=Prompts.REFINE_PROMPT.value.template,
        similarity_top_k=2,
    )

    response = await engine.aquery(query)
    return QueryResponse(response=str(response))


@index_app.post("/{index_name}/update")
async def update_doc(nodeId, index=Depends(get_index), text: str = Form()):
    try:
        updateNodeById(index, nodeId, text)
    except (ValueError, KeyError):
        return JSONResponse(content={'status': 'detail', 'message': 'node_id not exist'},
                            status_code=status.HTTP_404_NOT_FOUND)
    return JSONResponse(content={"status": "updated"})


@index_app.post("/{index_name}/uploadFile", response_model=UploadResponse)
async def upload_file(index=Depends(get_index), file: UploadFile = File(...)):
    try:
        validate_upload_file(file)
    except (FileTooLargeError, InvalidFileTypeError) as e:
        return JSONResponse(content={"status": "detail", "message": str(e)},
                            status_code=status.HTTP_400_BAD_REQUEST)
    filepath = None
    try:
        filename = safe_filename(file.filename)
        unique_id = str(uuid.uuid4())
        filepath = os.path.join(LOAD_PATH, f"{unique_id}_{filename}")
        savepath = os.path.join(SAVE_PATH, filename)
        file_bytes = await file.read()
        async with aiofiles.open(filepath, 'wb') as f:
            await f.write(file_bytes)
        async with aiofiles.open(savepath, 'wb') as f:
            await f.write(file_bytes)
        await insert_into_index(index, filepath)
    except Exception as e:
        logging.error(f"Error while handling file: {str(e)}")
        return JSONResponse(content={"status": "detail", "message": "Error while handling file: {}".format(str(e))},
                            status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)
    return UploadResponse(status="inserted")


@index_app.post("/{index_name}/uploadFiles", response_model=UploadResponse)
async def upload_files(index=Depends(get_index), files: List[UploadFile] = File(...)):
    filepaths = []
    try:
        for file in files:
            try:
                validate_upload_file(file)
            except (FileTooLargeError, InvalidFileTypeError) as e:
                return JSONResponse(content={"status": "detail", "message": str(e)},
                                    status_code=status.HTTP_400_BAD_REQUEST)
            filename = safe_filename(file.filename)
            unique_id = str(uuid.uuid4())
            filepath = os.path.join(LOAD_PATH, f"{unique_id}_{filename}")
            savepath = os.path.join(SAVE_PATH, index.index_id, filename)
            file_bytes = await file.read()
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(file_bytes)
            if not os.path.exists(savepath):
                os.makedirs(os.path.dirname(savepath), exist_ok=True)
            async with aiofiles.open(savepath, 'wb') as f:
                await f.write(file_bytes)
            filepaths.append(filepath)
        for fp in filepaths:
            await insert_into_index(index, fp)

    except Exception as e:
        return JSONResponse(content={"status": "detail", "message": f"Error while handling file: {str(e)}"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        for filepath in filepaths:
            if filepath is not None and os.path.exists(filepath):
                os.remove(filepath)

    return UploadResponse(status="inserted")


@index_app.post("/{index_name}/upload_file_by_QA")
async def upload_qa(index=Depends(get_index), prompt: str = Form(None), file: UploadFile = File(...)):
    contents = await read_file_contents(file)
    safe_prompt = build_qa_generation_prompt(prompt)
    qa_pairs = await generate_qa_batched(contents, safe_prompt)
    qa_data = formatted_pairs(qa_pairs)
    id = extract_content_after_backslash(file.filename)
    embeddingQA(index, qa_data, id)
    return {"status": 'ok'}


@index_app.post("/{index_name}/deleteDoc")
async def delete_doc(doc_id: str = Form(), index=Depends(get_index)):
    documents = get_all_docs(index)
    doc_ids = list(set(doc["doc_id"] for doc in documents))
    if doc_id not in doc_ids:
        return JSONResponse(content={"status": "detail", "message": "doc_id: not found"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    try:
        deleteDocById(index, doc_id)
    except Exception as e:
        return JSONResponse(content={"status": "detail", "message": f"delete doc error: {e}"},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return {"status": "deleted"}


@index_app.post("/{index_name}/deleteNode")
async def delete_node(node_id: str = Form(), index=Depends(get_index)):
    try:
        deleteNodeById(index, node_id)
        return {"status": "deleted"}
    except Exception:
        return JSONResponse(content={"status": "detail", "message": "node_id: not found"},
                            status_code=status.HTTP_400_BAD_REQUEST)


@index_app.get("/{index_name}/get_summary")
async def get_summary(index=Depends(get_index)):
    return {"summary": index.summary}


@index_app.post("/{index_name}/set_summary")
async def set_summary(index=Depends(get_index), summary: str = Form()):
    index.summary = summary
    saveIndex(index)
    return {"status": "ok", "summary": index.summary}


@index_app.post("/{index_name}/generate_summary")
async def generate_summary(index=Depends(get_index)):
    summary = await summary_index(index)
    index.summary = summary
    saveIndex(index)
    return {"status": "ok", "summary": summary}


@index_app.post("/{index_name}/insertdoc")
async def insert_docs(text=Form(), doc_id=Form(None), index=Depends(get_index)):
    if doc_id is None:
        doc = Document(text=text)
    else:
        doc_id = doc_id.replace("\\\\", "\\")
        doc = Document(text=text, doc_id=doc_id)
    index.insert_nodes([doc])
    saveIndex(index)
    return {"status": "ok"}


@index_app.post("/{index_name}/save")
async def save_index(index=Depends(get_index)):
    saveIndex(index)
    return {"status": "ok"}


@index_app.post("/{index_name}/getfile")
async def get_file(index=Depends(get_index)):
    await citf(index, f"{index.index_id}.txt")
    return {"status": "ok"}


@index_app.post("/{index_name}/evaluator")
async def evaluator(index=Depends(get_index), query: str = Form()):
    from llama_index.core.evaluation import ResponseEvaluator

    llm = build_llm()
    evaluator = ResponseEvaluator(llm=llm)
    query_engine = index.as_query_engine()
    response = await query_engine.aquery(query)
    eval_result = await evaluator.aevaluate(response=response, query=query)
    return {"result": str(eval_result)}
