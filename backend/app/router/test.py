import os
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File
from llama_index.core import Settings
from llama_index.core.schema import TextNode
from starlette import status
from starlette.responses import JSONResponse

from configs.load_env import LOAD_PATH, SAVE_PATH
from dependencies import get_index
from handlers.llama_handler import insert_into_index, summary_index
from utils.file import safe_filename
from utils.llama import get_nodes_from_file, formatted_pairs

test_app = APIRouter()


@test_app.post("/{index_name}/uploadFile")
async def upload_file(file: UploadFile = File(...)):
    filepath = None
    try:
        filename = safe_filename(file.filename)
        filepath = os.path.join(LOAD_PATH, filename)
        savepath = os.path.join(SAVE_PATH, filename)
        file_bytes = await file.read()
        with open(filepath, 'wb') as f:
            f.write(file_bytes)
        with open(savepath, 'wb') as f:
            f.write(file_bytes)

        nodes = get_nodes_from_file(filepath)
        return nodes
    except Exception as e:
        return JSONResponse(content={"status": "detail", "message": "Error while handling file: {}".format(str(e))},
                            status_code=status.HTTP_400_BAD_REQUEST)

    finally:
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)


@test_app.post("/{index_name}/insert_into_index")
async def confirm_modification(nodes: List[TextNode], index=Depends(get_index)):
    try:
        index.insert_nodes(nodes)
        return {"status": "inserted"}
    except Exception as e:
        return JSONResponse(
            content={"status": "detail", "message": "Error while inserting nodes: {}".format(str(e))},
            status_code=status.HTTP_400_BAD_REQUEST)
