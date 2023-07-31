import shutil

from fastapi import APIRouter, Form, File, UploadFile, status, Depends
from starlette.responses import JSONResponse

from handlers.handler import *
from dependencies import get_index

index_app = APIRouter()


async def startup_event():
    # 启动时加载一次索引
    loadAllIndexes(index_save_directory)
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
    loadAllIndexes(index_save_directory)
    return {"status": "ok", "load": "ok"}


@index_app.get("/index/list")
def get_index_list():
    path = os.path.join(PROJECT_ROOT, index_save_directory)
    list = get_subfolders_list(path)
    return JSONResponse(content={'indexes': list})


@index_app.post("/create")
async def create_index(index_name: str = Form()):
    """
    创建一个索引
    :param index_name: 索引名称
    :return:
    """
    createIndex(index_name)
    loadAllIndexes(index_save_directory)
    return index_name


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
    if index_name in get_subfolders_list(index_save_directory):
        index_path = os.path.join(index_save_directory, index_name)
        shutil.rmtree(index_path)
        loadAllIndexes(index_save_directory)
        return {"status": "deleted"}
    else:
        return JSONResponse(content={'status': 'detail', 'message': 'index not exist'},
                            status_code=status.HTTP_404_NOT_FOUND)


@index_app.post("/{index_name}/query")
async def query_index(index=Depends(get_index), query: str = Form()):
    engine = index.as_query_engine(text_qa_template=Prompt(Prompts.QA_PROMPT))
    return await engine.aquery(query)


@index_app.post("/{index_name}/update")
async def insert_doc(nodeId, index=Depends(get_index), text: str=Form()):
    """
    将文档插入到索引中
    :param index_name: 索引名称
    :param nodeId: 文档id
    :param text: 更新内容
    :return:
    """
    try:
        updateById(index, nodeId, text)
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
        filename = file.filename  # Generate a safe filename
        filepath = os.path.join(LOAD_PATH, filename)
        savepath = os.path.join(SAVE_PATH, filename)
        file_bytes = await file.read()
        with open(filepath, 'wb') as f:
            f.write(file_bytes)
        with open(savepath, 'wb') as f:
            f.write(file_bytes)
        logging.info("File {} has been saved to {}".format(filename, savepath))
        logging.info("filepath{}".format(LOAD_PATH))
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


@index_app.post("/{index_name}/delete")
async def delete_doc(doc_id, index=Depends(get_index)):
    deleteDocById(index, doc_id)
    return {"status": "deleted"}


@index_app.post("/{index_name}/get_summary")
async def set_summary(index=Depends(get_index), ):
    return {"summary": index.summary}


@index_app.post("/{index_name}/set_summary")
async def set_summary(index=Depends(get_index), summary: str = Form()):
    index.summary = summary
    return {"status": "ok", "summary": index.summary}


@index_app.post("/{index_name}/generate_summary")
async def set_summary(index=Depends(get_index)):
    summary = summary_index(index)
    return {"status": "ok", "summary": summary}


# @index_app.post("/{index_name}/insertdocs")
# async def insert_docs(index_name,path):
#     index = get_index_by_name(index_name)
#     insert_into_index(index,"path")
#     return {"status":"ok"}

@index_app.post("/{index_name}/insertdoc")
async def insert_docs(text, index=Depends(get_index)):
    doc = Document(text=text)
    index.insert(doc)
    return {"status": "ok"}


@index_app.post("/{index_name}/save")
async def save_index(index=Depends(get_index)):
    saveIndex(index)
    return {"status": "ok"}


graph = None


@index_app.post("/graph_query")
async def query_graph(query: str = Form()):
    global graph
    if graph is None:
        graph = compose_indices_to_graph()
    return await graph.achat(query)


@index_app.post("/graph_query_history")
async def query_graph():
    global graph
    if graph is None:
        return JSONResponse(content={"status": "detail", "message": "No query graph available"},
                            status_code=status.HTTP_404_NOT_FOUND)
    return get_history_msg(graph)


if __name__ == '__main__':
    print(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
