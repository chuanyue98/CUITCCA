from fastapi import Path

from app.handlers.handler import get_index_by_name


def get_index(index_name: str = Path()):
    index = get_index_by_name(index_name)
    return index
