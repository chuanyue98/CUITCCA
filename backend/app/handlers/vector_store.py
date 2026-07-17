import os

import chromadb
import configs.load_env as load_env
from configs.load_env import chroma_db_path
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.vector_stores.chroma import ChromaVectorStore

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


def _docstore_persist_path(index_name: str) -> str:
    # index_save_directory 用 load_env.X 属性访问而不是 from...import：
    # reload_env_variables() 热重载改的是 configs.load_env 模块内的变量，
    # from...import 在导入时就把值拷贝进了当前命名空间，之后源模块改了值这里
    # 感知不到（同样的坑见 handlers/graph_builder.py 顶部注释）。
    return os.path.join(load_env.index_save_directory, f"{index_name}_docstore.json")


def load_or_create_docstore(index_name: str) -> SimpleDocumentStore:
    """加载某个索引持久化的增量摄取 docstore；不存在则新建一个空的。

    这个 docstore 只用于 ``IngestionPipeline`` 的 ``DocstoreStrategy.UPSERTS``
    判断（doc_id -> 内容 hash，判断"内容没变就跳过"），不是节点的权威存储——
    Chroma collection 才是。丢失/清空这个文件只会让下一次摄取把所有内容当成
    "新的"重新写一遍（幂等，不丢数据），不是灾难性故障。
    """
    path = _docstore_persist_path(index_name)
    if os.path.exists(path):
        return SimpleDocumentStore.from_persist_path(path)
    return SimpleDocumentStore()


def persist_docstore(index_name: str, docstore: SimpleDocumentStore) -> None:
    os.makedirs(load_env.index_save_directory, exist_ok=True)
    docstore.persist(_docstore_persist_path(index_name))
