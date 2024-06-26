from fastapi import Path, HTTPException
from llama_index.core.indices.base import BaseIndex
from starlette import status

from handlers.llama_handler import get_index_by_name, loadAllIndexes


def get_index(index_name: str = Path()) -> BaseIndex:
    loadAllIndexes()
    index = get_index_by_name(index_name)
    if index is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='index not exist')
    return index
