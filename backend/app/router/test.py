import asyncio
import os
import re
from typing import List

import openai
from fastapi import APIRouter, Depends, UploadFile, File
from langchain.chat_models import ChatOpenAI
from langchain.text_splitter import SpacyTextSplitter
from llama_index import SimpleDirectoryReader, LLMPredictor, ServiceContext
from llama_index.indices.base import BaseIndex
from llama_index.llms import ChatMessage, OpenAI
from llama_index.schema import TextNode, Document
from starlette import status
from starlette.responses import JSONResponse

from configs.embed_model import EmbedModelOption
from configs.llm_predictor import LLMPredictorOption
from configs.load_env import LOAD_PATH, SAVE_PATH, index_save_directory
from dependencies import get_index
from handlers.llama_handler import insert_into_index, summary_index
from utils.llama import get_nodes_from_file

test_app = APIRouter()


@test_app.post("/{index_name}/uploadFile")
async def upload_file(file: UploadFile = File(...)):
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

        # 获取节点列表
        nodes = get_nodes_from_file(LOAD_PATH)

        # 返回新列表给前端展示修改
        return nodes
    except Exception as e:
        return JSONResponse(content={"status": "detail", "message": "Error while handling file: {}".format(str(e))},
                            status_code=status.HTTP_400_BAD_REQUEST)

    finally:
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)


@test_app.post("/{index_name}/insert_into_index")
async def confirm_modification(nodes: List[TextNode], index=Depends(get_index)):
    """
    确认修改后的节点列表并插入索引
    :param index: 索引
    :param nodes: 修改后的节点列表
    :return:
    """
    llm_predictor = LLMPredictor(
        llm=ChatOpenAI(temperature=0.1, model_name="gpt-3.5-turbo-16k", max_tokens=1024, openai_api_key=openai.api_key))
    try:
        service_context = ServiceContext.from_defaults(llm_predictor=llm_predictor)
        index.insert_nodes(nodes, context=service_context)
        return {"status": "inserted"}

    except Exception as e:
        return JSONResponse(
            content={"status": "detail", "message": "Error while inserting nodes: {}".format(str(e))},
            status_code=status.HTTP_400_BAD_REQUEST)




@test_app.post("/qa_generate")
async def qa_generate(file: UploadFile = File(...)):
    contents = await file.read()
    contents = contents.decode("utf-8")
    # 分批生成 QA
    qa_pairs = await generate_qa_batched(contents)

    return {"qa_pairs": qa_pairs}







if __name__ == '__main__':
    p = """Q: 我校有多少担任校外兼职博士生导师？
A: 我校有 28 人担任校外兼职博士生导师。
Q: 我校有多少比较有影响力的主要学术兼职？
A: 我校有 46 项比较有影响力的主要学术兼职。"""
    print(formatted_pairs(p))
