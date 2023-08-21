import shutil
from typing import List

import aiofiles
from fastapi import APIRouter, Form, File, UploadFile, status, Depends
from llama_index.evaluation import ResponseEvaluator
from llama_index.indices.postprocessor import SentenceEmbeddingOptimizer
from starlette.responses import JSONResponse

from configs.load_env import index_save_directory, SAVE_PATH, LOAD_PATH, PROJECT_ROOT
from handlers.llama_handler import *
from dependencies import get_index
from utils.llama import formatted_pairs, generate_qa_batched

index_app = APIRouter()


async def startup_event():
    # 启动时加载一次索引
    loadAllIndexes()
    # 创建所需目录
    import os
    # 检查和创建目录
    for directory in [index_save_directory, SAVE_PATH, LOAD_PATH]:
        if not os.path.exists(directory):
            os.makedirs(directory)


@index_app.on_event("startup")
async def startup():
    """启动时加载一次索引"""
    await startup_event()


@index_app.get("/")
async def index():
    """
    加载索引
    :return:
    """
    loadAllIndexes()
    return {"status": "ok", "load": "ok"}


@index_app.get("/index/list")
def get_index_list():
    path = os.path.join(PROJECT_ROOT, index_save_directory)
    list = get_folders_list(path)
    return JSONResponse(content={'indexes': list})


@index_app.post("/create")
async def create_index(index_name: str = Form()):
    """
    创建一个索引
    :param index_name: 索引名称
    :return:
    """
    if index_name in get_folders_list(index_save_directory):
        return JSONResponse(content={'status': 'error', 'msg': 'index already exists'})
    createIndex(index_name)
    loadAllIndexes()
    return JSONResponse(content={'status': 'success', 'msg': f'index {index_name} created'})


@index_app.get("/{index_name}/info")
async def index_info(index=Depends(get_index)):
    """
    索引信息
    :param index_name:
    :return:
    """
    docs = get_all_docs(index)
    return JSONResponse(content={'docs': docs}, status_code=status.HTTP_200_OK)


@index_app.post("/delete")
def delete_index(index_name: str = Form()):
    """
    删除一个索引
    :param index_name: 索引名称
    :return:
    """
    if index_name in get_folders_list(index_save_directory):
        index_path = os.path.join(index_save_directory, index_name)
        shutil.rmtree(index_path)
        loadAllIndexes()
        return {"status": "deleted"}
    else:
        return JSONResponse(content={'status': 'detail', 'message': 'index not exist'},
                            status_code=status.HTTP_404_NOT_FOUND)


@index_app.post("/{index_name}/query")
async def query_index(index=Depends(get_index), query: str = Form()):
    """
    查询索引
    :param index_name: 索引名称
    :param query: 查询语句
    :return:
    """
    engine = index.as_query_engine(text_qa_template=Prompts.QA_PROMPT.value)
    return await engine.aquery(query)

@index_app.post("/{index_name}/query_stream")
async def query_stream(index: BaseIndex = Depends(get_index), query: str = Form()):
    """
    Streaming not supported for async
    """
    engine = index.as_query_engine(streaming=True,text_qa_template=Prompts.QA_PROMPT.value,node_postprocessors=[SentenceEmbeddingOptimizer(percentile_cutoff=0.5)])
    res = engine.query(query)
    return res.response_gen


@index_app.post("/{index_name}/update")
async def update_doc(nodeId, index=Depends(get_index), text: str=Form()):
    """
    将文档插入到索引中
    :param index_name: 索引名称
    :param nodeId: 文档id
    :param text: 更新后的内容
    :return:
    """
    try:
        updateNodeById(index, nodeId, text)
    except ValueError:
        return JSONResponse(content={'status': 'detail', 'message': 'node_id not exist'},
                           status_code=status.HTTP_404_NOT_FOUND)
    return JSONResponse(content={"status": "updated"})


@index_app.post("/{index_name}/uploadFile")
async def upload_file(index=Depends(get_index), file: UploadFile = File(...)):
    """
    上传文件到索引中
    :param index: 索引
    :param file: 文件对象
    :return:
    """
    filepath = None
    try:
        filename = file.filename
        filepath = os.path.join(LOAD_PATH, filename)
        savepath = os.path.join(SAVE_PATH, filename)
        file_bytes = await file.read()
        with open(filepath, 'wb') as f:
            f.write(file_bytes)
        with open(savepath, 'wb') as f:
            f.write(file_bytes)
        insert_into_index(index, LOAD_PATH)
    except Exception as e:
        logging.error(f"Error while handling file: {str(e)}")  # Log the error
        return JSONResponse(content={"status": "detail", "message": "Error while handling file: {}".format(str(e))},
                            status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        # Always cleanup the temp file
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)
    return {"status": "inserted"}



@index_app.post("/{index_name}/uploadFiles")
async def upload_files(index=Depends(get_index), files: List[UploadFile] = File(...)):
    """
    上传文件
    :param index_name: 索引名称
    :param files: List of file objects
    :return:
    """
    filepaths = []
    try:
        for file in files:
            filename = file.filename
            filepath = os.path.join(LOAD_PATH, filename)
            savepath = os.path.join(SAVE_PATH, filename)
            file_bytes = await file.read()
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(file_bytes)
            async with aiofiles.open(savepath, 'wb') as f:
                await f.write(file_bytes)

            filepaths.append(filepath)
        # TODO 每上传一个文件，通知前端..
        insert_into_index(index, LOAD_PATH)

    except Exception as e:
        return JSONResponse(content={"status": "detail", "message": f"Error while handling file: {str(e)}"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        # Always cleanup the temp files
        for filepath in filepaths:
            if filepath is not None and os.path.exists(filepath):
                os.remove(filepath)

    return {"status": "inserted"}



@index_app.post("{index_name}/upload_file_by_QA")
async def upload_qa(index=Depends(get_index),prompt: str = Form(None),file: UploadFile = File(...)):
    contents = await file.read()
    contents = contents.decode("utf-8")
    # 分批生成 QA
    qa_pairs = await generate_qa_batched(contents,prompt)
    qa_data = formatted_pairs(qa_pairs)
    embeddingQA(index,qa_data)
    return {"status": 'ok'}


@index_app.post("/{index_name}/deleteDoc")
async def delete_doc(doc_id, index=Depends(get_index)):
    """
    根据文档id删除文档
    :param doc_id:
    :param index:
    :return:
    """
    documents = get_all_docs(index)
    doc_ids = list(set(doc["doc_id"] for doc in documents))
    if doc_id not in doc_ids:
        return JSONResponse(content={"status": "detail", "message": f"doc_id: not found"},
                            status_code=status.HTTP_400_BAD_REQUEST)
    deleteDocById(index, doc_id)
    return {"status": "deleted"}

@index_app.post("/{index_name}/deleteNode")
async def delete_node(node_id, index=Depends(get_index)):
    """
    根据节点id删除节点
    :param node_id:
    :param index:
    :return:
    """
    try:
        deleteNodeById(index, node_id)
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse(content={"status": "detail", "message": f"node_id: not found"},
                            status_code=status.HTTP_400_BAD_REQUEST)

@index_app.get("/{index_name}/get_summary")
async def get_summary(index=Depends(get_index)):
    """
    获取索引的摘要信息
    :param index: 索引名称
    :return: 索引摘要
    """
    return {"summary": index.summary}


@index_app.post("/{index_name}/set_summary")
async def set_summary(index=Depends(get_index), summary: str = Form()):
    """
    设置索引的摘要信息
    :param index: 索引名称
    :param summary: 摘要信息
    :return: 索引摘要
    """
    index.summary = summary
    return {"status": "ok", "summary": index.summary}


@index_app.post("/{index_name}/generate_summary")
async def set_summary(index=Depends(get_index)):
    """
    使用gpt生成索引的摘要信息
    :param index: 索引名称
    :return: 索引摘要
    """
    index.generate_summary()
    summary = summary_index(index)
    return {"status": "ok", "summary": summary}


@index_app.post("/{index_name}/insertdoc")
async def insert_docs(text, index=Depends(get_index),doc_id = Form(None)):
    """
    插入文档
    :param text: 文本
    :param index: 索引名称
    :param doc_id: 文档id
    :return: 插入状态
    """
    if doc_id is None:
        doc = Document(text=text)
    else:
        doc_id = doc_id.replace("\\\\", "\\")
        doc = Document(text=text,doc_id=doc_id)
    index.insert(doc)
    return {"status": "ok"}


@index_app.post("/{index_name}/save")
async def save_index(index=Depends(get_index)):
    """
    保存索引
    :param index: 索引名称
    :return: 保存状态
    """
    index.save()
    saveIndex(index)
    return {"status": "ok"}

@index_app.post("/{index_name}/getfile")
async def get_file(index_name):
    """
    获取索引文件
    :param index_name: 索引名称
    :return:
    """
    convert_index_to_file(index_name,f"{index_name}.txt")
    return {"status": "ok"}

@index_app.post("/{index_name}/evaluator")
async def evaluator(index=Depends(get_index), query: str = Form()):
    service_context = ServiceContext.from_defaults(llm_predictor=LLMPredictorOption.DEFAULT.value)
    evaluator = ResponseEvaluator(service_context=service_context)
    query_engine = index.as_query_engine()
    response = query_engine.query(query)
    eval_result = evaluator.evaluate(response)
    return eval_result

if __name__ == '__main__':
    print(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
