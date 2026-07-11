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
    delete_index,
    get_docs_from_index,
)
from handlers.graph_builder import (
    compose_graph_chat_egine,
    compose_graph_query_engine,
    summary_index,
    get_history_msg,
)


def get_prompt_by_name(prompt_type):
    from configs.config import Prompts
    return getattr(Prompts, prompt_type.value).value
