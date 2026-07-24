import asyncio
import os
import re
import uuid

import aiofiles

# QUERY_ENDPOINT_TOP_K 故意不在这里用 from...import 直接绑定，理由见
# handlers/graph_builder.py 顶部同样的说明——那样绑定会让
# reload_env_variables() 之后这个值就再也感知不到环境变量变化了。
import configs.load_env as load_env
from configs.config import Prompts
from configs.llm_predictor import build_llm
from configs.load_env import LOAD_PATH, SAVE_PATH
from dependencies import get_index
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from handlers import delete_collection, list_index_names
from handlers.graph_builder import summary_index
from handlers.hybrid_retriever import build_retriever_for_index, invalidate_hybrid_retriever_cache
from handlers.index_crud import (
    _indexes_lock,
    citf,
    createIndex,
    deleteDocById,
    deleteNodeById,
    embeddingQA,
    get_all_docs,
    indexes,
    insert_into_index,
    loadAllIndexes,
    saveIndex,
    updateNodeById,
)
from llama_index.core import Document
from llama_index.core.query_engine import RetrieverQueryEngine
from models.response import IndexListResponse, QueryResponse, UploadResponse
from starlette.responses import JSONResponse
from utils.file import read_file_contents, safe_filename
from utils.llama import (
    build_qa_generation_prompt,
    extract_content_after_backslash,
    formatted_pairs,
    generate_qa_batched,
)
from utils.logger import customer_logger, error_logger
from utils.upload import FileTooLargeError, InvalidFileTypeError, validate_upload_file

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
async def create_index(index_name: str = Form(max_length=100)):
    sanitized_name = _sanitize_index_name(index_name)
    if sanitized_name in list_index_names():
        return JSONResponse(content={'status': 'error', 'msg': 'index already exists'})
    createIndex(sanitized_name)
    await loadAllIndexes()
    invalidate_hybrid_retriever_cache()
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
async def delete_index(index_name: str = Form(max_length=100)):
    sanitized_name = _sanitize_index_name(index_name)
    if sanitized_name in list_index_names():
        delete_collection(sanitized_name)
        await loadAllIndexes()
        invalidate_hybrid_retriever_cache()
        return {"status": "deleted"}
    else:
        return JSONResponse(content={'status': 'detail', 'message': 'index not exist'},
                            status_code=status.HTTP_404_NOT_FOUND)


@index_app.post("/{index_name}/query", response_model=QueryResponse)
async def query_index(index=Depends(get_index), query: str = Form(max_length=5000)):
    customer_logger.info(f"query index {index.index_id} with query {query}")

    retriever = build_retriever_for_index(index, load_env.QUERY_ENDPOINT_TOP_K)
    engine = RetrieverQueryEngine.from_args(
        retriever=retriever,
        text_qa_template=Prompts.QA_PROMPT.value,
        refine_template=Prompts.REFINE_PROMPT.value,
    )

    response = await engine.aquery(query)
    return QueryResponse(response=str(response))


@index_app.post("/{index_name}/update")
async def update_doc(nodeId, index=Depends(get_index), text: str = Form(max_length=10000)):
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
    savepath = None
    try:
        filename = safe_filename(file.filename)
        unique_id = str(uuid.uuid4())
        os.makedirs(LOAD_PATH, exist_ok=True)
        filepath = os.path.join(LOAD_PATH, f"{unique_id}_{filename}")
        savepath = os.path.join(SAVE_PATH, index.index_id, filename)
        os.makedirs(os.path.dirname(savepath), exist_ok=True)
        file_bytes = await file.read()
        async with aiofiles.open(filepath, 'wb') as f:
            await f.write(file_bytes)
        async with aiofiles.open(savepath, 'wb') as f:
            await f.write(file_bytes)
        await insert_into_index(index, filepath)
        invalidate_hybrid_retriever_cache()
    except Exception as e:
        error_logger.error(f"Error while handling file: {str(e)}")
        if savepath is not None and os.path.exists(savepath):
            os.remove(savepath)
        return JSONResponse(content={"status": "detail", "message": "文件处理出错，请检查文件格式或联系管理员"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)
    return UploadResponse(status="inserted")


@index_app.post("/{index_name}/uploadFiles", response_model=UploadResponse)
async def upload_files(index=Depends(get_index), files: list[UploadFile] = File(...)):
    filepaths = []
    saved_paths = []
    try:
        for file in files:
            try:
                validate_upload_file(file)
            except (FileTooLargeError, InvalidFileTypeError) as e:
                return JSONResponse(content={"status": "detail", "message": str(e)},
                                    status_code=status.HTTP_400_BAD_REQUEST)
            filename = safe_filename(file.filename)
            unique_id = str(uuid.uuid4())
            os.makedirs(LOAD_PATH, exist_ok=True)
            filepath = os.path.join(LOAD_PATH, f"{unique_id}_{filename}")
            savepath = os.path.join(SAVE_PATH, index.index_id, filename)
            file_bytes = await file.read()
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(file_bytes)
            os.makedirs(os.path.dirname(savepath), exist_ok=True)
            async with aiofiles.open(savepath, 'wb') as f:
                await f.write(file_bytes)
            filepaths.append(filepath)
            saved_paths.append(savepath)

        # 批量插入，最后一次摘要生成（避免 N+1 LLM 调用）
        for fp in filepaths:
            await insert_into_index(index, fp, skip_summary=True)
        # 所有文件插入完成后，生成一次摘要
        from handlers.graph_builder import summary_index
        index.summary = await summary_index(index)
        from handlers.index_crud import _save_summary
        _save_summary(index)
        invalidate_hybrid_retriever_cache()

    except Exception as e:
        error_logger.error(f"Error while handling files: {str(e)}")
        # 回滚已写入的永久文件
        for sp in saved_paths:
            if os.path.exists(sp):
                os.remove(sp)
        return JSONResponse(content={"status": "detail", "message": "文件处理出错，请检查文件格式或联系管理员"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        for filepath in filepaths:
            if filepath is not None and os.path.exists(filepath):
                os.remove(filepath)

    return UploadResponse(status="inserted")


@index_app.post("/{index_name}/upload_file_by_QA")
async def upload_qa(index=Depends(get_index), prompt: str = Form(None, max_length=5000), file: UploadFile = File(...)):
    contents = await read_file_contents(file)
    safe_prompt = build_qa_generation_prompt(prompt)
    qa_pairs = await generate_qa_batched(contents, safe_prompt)
    qa_data = formatted_pairs(qa_pairs)
    id = extract_content_after_backslash(file.filename)
    await embeddingQA(index, qa_data, id)
    return {"status": 'ok'}


@index_app.post("/{index_name}/deleteDoc")
async def delete_doc(doc_id: str = Query(max_length=200), index=Depends(get_index)):
    documents = get_all_docs(index)
    doc_ids = list(set(doc["doc_id"] for doc in documents))
    if doc_id not in doc_ids:
        return JSONResponse(content={"status": "detail", "message": "doc_id: not found"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    try:
        deleteDocById(index, doc_id)
    except Exception as e:
        error_logger.error(f"delete doc error: {e}")
        return JSONResponse(content={"status": "detail", "message": "删除文档时出错"},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    invalidate_hybrid_retriever_cache()
    return {"status": "deleted"}


@index_app.post("/{index_name}/deleteNode")
async def delete_node(node_id: str = Query(max_length=200), index=Depends(get_index)):
    try:
        deleteNodeById(index, node_id)
    except Exception:
        return JSONResponse(content={"status": "detail", "message": "node_id: not found"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    invalidate_hybrid_retriever_cache()
    return {"status": "deleted"}


@index_app.get("/{index_name}/get_summary")
async def get_summary(index=Depends(get_index)):
    return {"summary": index.summary}


@index_app.post("/{index_name}/set_summary")
async def set_summary(index=Depends(get_index), summary: str = Form(max_length=5000)):
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
async def insert_docs(
    text: str = Form(max_length=50000),
    doc_id: str = Form(None, max_length=200),
    index=Depends(get_index),
):
    if doc_id is None:
        doc = Document(text=text)
    else:
        doc_id = doc_id.replace("\\\\", "\\")
        doc = Document(text=text, doc_id=doc_id)
    from handlers.index_crud import _get_index_lock
    lock = await _get_index_lock(index.index_id)
    async with lock:
        await asyncio.to_thread(index.insert_nodes, [doc])
        saveIndex(index)
    invalidate_hybrid_retriever_cache()
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
async def evaluator(index=Depends(get_index), query: str = Form(max_length=5000)):
    from llama_index.core.evaluation import ResponseEvaluator

    llm = build_llm()
    evaluator = ResponseEvaluator(llm=llm)
    query_engine = index.as_query_engine()
    response = await query_engine.aquery(query)
    eval_result = await evaluator.aevaluate(response=response, query=query)
    return {"result": str(eval_result)}
