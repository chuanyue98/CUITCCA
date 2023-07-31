from fastapi import Path, HTTPException
from llama_index.indices.base import BaseIndex
from starlette import status

from app.handlers.handler import get_index_by_name


def get_index(index_name: str = Path()) -> BaseIndex:
    index = get_index_by_name(index_name)
    if index is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='index not exist')
    return index
