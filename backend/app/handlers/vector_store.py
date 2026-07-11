import chromadb
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.chroma import ChromaVectorStore

from configs.load_env import chroma_db_path

_client_instance = None


def _get_client():
    global _client_instance
    if _client_instance is None:
        _client_instance = chromadb.PersistentClient(path=chroma_db_path)
    return _client_instance


def get_or_create_collection(name: str):
    client = _get_client()
    return client.get_or_create_collection(name)


def list_index_names() -> list[str]:
    client = _get_client()
    return [c.name for c in client.list_collections()]


def delete_collection(name: str):
    client = _get_client()
    client.delete_collection(name)


def build_index_from_collection(collection) -> VectorStoreIndex:
    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=Settings.embed_model,
    )
    return index


def create_empty_index(index_name: str) -> VectorStoreIndex:
    collection = get_or_create_collection(index_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=Settings.embed_model,
    )
    index.set_index_id(index_name)
    return index
