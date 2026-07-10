import os
import shutil
import re
import uuid
from typing import List

import aiofiles
import torch
from fastapi import APIRouter, Form, File, UploadFile, status, Depends, HTTPException
from llama_index.core.evaluation import ResponseEvaluator
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import Settings, Document
from starlette.responses import JSONResponse

from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from configs.load_env import index_save_directory, SAVE_PATH, LOAD_PATH, PROJECT_ROOT, LOG_PATH
from configs.llm_predictor import build_llm, init_settings
from handlers.llama_handler import (
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
from dependencies import get_index
from utils.file import read_file_contents, safe_filename, get_folders_list
from utils.llama import formatted_pairs, generate_qa_batched, extract_content_after_backslash, \
    build_qa_generation_prompt

index_app = APIRouter()


def _sanitize_index_name(name: str) -> str:
    return re.sub(r'[^\w\-]', '_', name)


@index_app.get("/")
async def index():
    return {"status": "ok", "load": "ok"}


@index_app.get("/list")
async def get_index_list():
    async with _indexes_lock:
        index_list = [index.index_id for index in indexes]
    return JSONResponse(content={'indexes': index_list})


@index_app.post("/create")
async def create_index(index_name: str = Form()):
    sanitized_name = _sanitize_index_name(index_name)
    if sanitized_name in get_folders_list(index_save_directory):
        return JSONResponse(content={'status': 'error', 'msg': 'index already exists'})
    createIndex(sanitized_name)
    await loadAllIndexes()
    return JSONResponse(content={'status': 'success', 'msg': f'index {sanitized_name} created'})


@index_app.get("/{index_name}/info")
async def index_info(index=Depends(get_index)):
    docs = get_all_docs(index)
    return JSONResponse(content={'docs': docs}, status_code=status.HTTP_200_OK)


@index_app.post("/delete")
async def delete_index(index_name: str = Form()):
    if index_name in get_folders_list(index_save_directory):
        index_path = os.path.join(index_save_directory, index_name)
        shutil.rmtree(index_path)
        await loadAllIndexes()
        return {"status": "deleted"}
    else:
        return JSONResponse(content={'status': 'detail', 'message': 'index not exist'},
                            status_code=status.HTTP_404_NOT_FOUND)


@index_app.post("/{index_name}/query")
async def query_index(index=Depends(get_index), query: str = Form()):
    customer_logger.info(f"query index {index.index_id} with query {query}")

    engine = index.as_query_engine(
        text_qa_template=Prompts.QA_PROMPT.value,
        refine_template=Prompts.REFINE_PROMPT.value,
        similarity_top_k=2,
    )

    response = await engine.aquery(query)
    return {"response": str(response)}


@index_app.post("/{index_name}/update")
async def update_doc(nodeId, index=Depends(get_index), text: str = Form()):
    try:
        updateNodeById(index, nodeId, text)
    except (ValueError, KeyError):
        return JSONResponse(content={'status': 'detail', 'message': 'node_id not exist'},
                            status_code=status.HTTP_404_NOT_FOUND)
    return JSONResponse(content={"status": "updated"})


@index_app.post("/{index_name}/uploadFile")
async def upload_file(index=Depends(get_index), file: UploadFile = File(...)):
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
    return {"status": "inserted"}


@index_app.post("/{index_name}/uploadFiles")
async def upload_files(index=Depends(get_index), files: List[UploadFile] = File(...)):
    filepaths = []
    try:
        for file in files:
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

    return {"status": "inserted"}


@index_app.post("/{index_name}/upload_file_by_QA")
async def upload_qa(index=Depends(get_index), prompt: str = Form(None), file: UploadFile = File(...)):
    contents = read_file_contents(file)
    safe_prompt = build_qa_generation_prompt(prompt)
    qa_pairs = await generate_qa_batched(contents, safe_prompt)
    qa_data = formatted_pairs(qa_pairs)
    id = extract_content_after_backslash(file.filename)
    embeddingQA(index, qa_data, id)
    return {"status": 'ok'}


@index_app.post("/{index_name}/deleteDoc")
async def delete_doc(doc_id, index=Depends(get_index)):
    documents = get_all_docs(index)
    doc_ids = list(set(doc["doc_id"] for doc in documents))
    if doc_id not in doc_ids:
        return JSONResponse(content={"status": "detail", "message": f"doc_id: not found"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    try:
        deleteDocById(index, doc_id)
    except Exception as e:
        return JSONResponse(content={"status": "detail", "message": f"delete doc error: {e}"})
    return {"status": "deleted"}


@index_app.post("/{index_name}/deleteNode")
async def delete_node(node_id, index=Depends(get_index)):
    try:
        deleteNodeById(index, node_id)
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse(content={"status": "detail", "message": f"node_id: not found"},
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
    index.insert(doc)
    saveIndex(index)
    return {"status": "ok"}


@index_app.post("/{index_name}/save")
async def save_index(index=Depends(get_index)):
    saveIndex(index)
    return {"status": "ok"}


@index_app.post("/{index_name}/getfile")
async def get_file(index=Depends(get_index)):
    citf(index, f"{index.index_id}.txt")
    return {"status": "ok"}


@index_app.post("/{index_name}/evaluator")
async def evaluator(index=Depends(get_index), query: str = Form()):
    evaluator = ResponseEvaluator()
    query_engine = index.as_query_engine()
    response = query_engine.query(query)
    eval_result = evaluator.evaluate(response)
    return {"result": str(eval_result)}
