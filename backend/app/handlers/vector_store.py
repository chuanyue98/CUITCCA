import os
import shutil

import chromadb
import configs.load_env as load_env
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.vector_stores.chroma import ChromaVectorStore

_client_instance = None


def _get_client():
    global _client_instance
    if _client_instance is None:
        _client_instance = chromadb.PersistentClient(path=load_env.chroma_db_path)
    return _client_instance


def get_or_create_collection(name: str, metadata: dict | None = None):
    """取（不存在则创建）一个 Chroma collection。

    ``metadata`` 只对**新建**的 collection 生效（Chroma 对已存在的 collection
    忽略创建参数）——qa_cache 用它在创建时指定 cosine 距离空间，语义缓存需要
    余弦相似度做阈值判断，默认的 L2 距离没有"相似度"语义。
    """
    client = _get_client()
    return client.get_or_create_collection(name, metadata=metadata)


def list_index_names() -> list[str]:
    client = _get_client()
    return [c.name for c in client.list_collections()]


def delete_collection(name: str):
    client = _get_client()
    client.delete_collection(name)
    # 顺带清理该索引的增量摄取 docstore 持久化文件（{name}_docstore.json）。
    # 不删的话：删除索引后重建同名索引、再上传相同内容，会被残留 docstore 的
    # UPSERTS 判重静默跳过——接口返回 {"status": "inserted"} 但实际 0 节点
    # 入库（实测可复现：ingest pipeline 拿旧内容 hash 判断"没变"就跳过插入，
    # 管理页节点列表随之空转）。docstore 文件丢失是幂等安全的（顶多把内容
    # 重新写一遍，不丢数据），所以这里宁可删掉也不让残留。
    try:
        os.remove(_docstore_persist_path(name))
    except FileNotFoundError:
        pass
    # 连带清理 SAVE_PATH 下该索引的源文件目录（{SAVE_PATH}/{name}/，上传时
    # 按 index.index_id 落盘，见 router/index.py uploadFiles）。跟 docstore 是
    # 同类"删除不彻底"问题：不删的话磁盘上会积累孤儿文件，重建同名索引后
    # 目录里还可能躺着旧索引的源文件，让人误以为它们属于新索引。目录丢失
    # 是幂等安全的（只是上传的原始文件副本，重新上传即可），这里宁可删掉
    # 也不留孤儿。目录不存在时静默跳过。
    #
    # 守卫必须要求 SAVE_PATH 非空 + 目标确实在 SAVE_PATH 内部：模块级默认
    # SAVE_PATH 是空串（reload_env_variables 才填值），空串下 os.path.join
    # 会返回裸 name，直接 rmtree 会把 CWD 下的同名目录干掉。
    if load_env.SAVE_PATH:
        source_dir = os.path.join(load_env.SAVE_PATH, name)
        if os.path.normpath(source_dir) != os.path.normpath(load_env.SAVE_PATH):
            try:
                shutil.rmtree(source_dir)
            except (FileNotFoundError, NotADirectoryError):
                pass


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
