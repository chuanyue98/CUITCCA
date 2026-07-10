from handlers.index_crud import (
    indexes,
    _indexes_lock,
    createIndex,
    loadAllIndexes,
    insert_into_index,
    embeddingQA,
    get_all_docs,
    updateNodeById,
    deleteNodeById,
    deleteDocById,
    saveIndex,
    get_index_by_name,
    convert_index_to_file,
    citf,
    format_source_nodes_list,
    fix_doc_id_not_found,
    get_docs_from_index,
)
from handlers.file_converters import (
    remove_vector_store,
    remove_index_store,
    remove_docstore,
)
from handlers.graph_builder import (
    compose_graph_chat_egine,
    compose_graph_query_engine,
    summary_index,
    get_history_msg,
)
from llama_index.core import load_index_from_storage, StorageContext
from configs.load_env import index_save_directory
from utils.file import get_folders_list


def get_prompt_by_name(prompt_type):
    """获取Prompt"""
    from configs.config import Prompts
    return getattr(Prompts, prompt_type.value).value
