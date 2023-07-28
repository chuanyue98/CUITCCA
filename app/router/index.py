from fastapi import APIRouter, Form, File, UploadFile
from starlette.responses import JSONResponse

from app.handlers.handler import *

index_app = APIRouter()

@index_app.get("/")
async def index():
    """
    加载索引
    :return:
    """
    loadAllIndexes(index_save_directory)
    return {"status": "ok","load":"ok"}

@index_app.get("/index/list")
def get_index_list():
    path = os.path.join(PROJECT_ROOT,index_save_directory)
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
async def index_info(index_name: str):
    """
    索引信息
    :param index_name:
    :return:
    """
    index = get_index_by_name(index_name)
    print("=======================================",index)
    docs = get_all_docs(index)
    return JSONResponse(content={'docs': docs})

@index_app.post("/{index_name}/query")
async def query_index(index_name: str, query: str = Form()):
    index = get_index_by_name(index_name)
    engine = index.as_query_engine(text_qa_template=QA_PROMPT_TMPL)
    return await engine.aquery(query)


@index_app.post("/{index_name}/update")
async def insert_doc(index_name, nodeId, text=Form()):
    """
    将文档插入到索引中
    :param index_name: 索引名称
    :param nodeId: 文档id
    :param text: 更新内容
    :return:
    """
    index = get_index_by_name(index_name)
    updateById(index,nodeId,text)
    return {"status": "ok"}


@index_app.post("/{index_name}/uploadFile")
async def upload_file(index_name, file: UploadFile = File(...)):
    """
    上传文件到索引中
    :param index_name: 索引名称
    :param file: 文件对象
    :return:
    """
    index = get_index_by_name(index_name)
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
        insert_into_index(index,LOAD_PATH)
    except Exception as e:
        logging.error(f"Error while handling file: {str(e)}")  # Log the error
        return "Error: {}".format(str(e)), 500
    finally:
        # Always cleanup the temp file
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)
    return "File inserted!", 200

@index_app.post("/{index_name}/delete")
async def delete_doc(index_name,doc_id):
    index = get_index_by_name(index_name)
    deleteDocById(index,doc_id)
    return {"status":"ok"}

@index_app.post("/{index_name}/summary")
async def set_summary(index_name: str, summary: str = Form()):
    index = get_index_by_name(index_name)
    index.summary = summary
    return {"status":"ok","summary" : index.summary}

@index_app.post("/{index_name}/insertdocs")
async def insert_docs(index_name,path):
    index = get_index_by_name(index_name)
    insert_into_index(index,"path")
    return {"status":"ok"}

@index_app.post("/{index_name}/insertdoc")
async def insert_docs(index_name,text):
    index = get_index_by_name(index_name)
    doc = Document(text=text)
    index.insert(doc)
    return {"status":"ok"}

@index_app.post("/{index_name}/save")
async def insert_docs(index_name):
    index = get_index_by_name(index_name)
    saveIndex(index)
    return {"status":"ok"}

graph = None
@index_app.post("/graph_query")
async def query_graph(query: str = Form()):
    global graph
    if graph is None:
        graph = compose_indices_to_graph()
    return await graph.achat(query)

@index_app.post("/graph_query_stream")
async def query_graph(query: str = Form()):
    global graph
    if graph is None:
        graph = compose_indices_to_graph()
    return await graph.astream_chat(query)



@index_app.post("/graph_query_history")
async def query_graph():
    global graph
    if graph is None:
        return {"status":"error","message":"No query graph available"}
    return get_history_msg(graph)





def get_index_by_name(index_name):
    index: VectorStoreIndex = None
    for i in indexes:
        if i.index_id == index_name:
            index = i
            break
    return index

if __name__ == '__main__':
    print(get_index_list())