from fastapi import HTTPException, Path
from handlers.index_crud import get_index_by_name
from llama_index.core.indices.base import BaseIndex
from starlette import status


def get_index(index_name: str = Path()) -> BaseIndex:
    index = get_index_by_name(index_name)
    if index is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='index not exist')
    return index
