import logging
import os

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

index_save_directory = ''
SAVE_PATH = ''
LOAD_PATH = ''
FEEDBACK_PATH = ''
LOG_PATH = ''
FILE_PATH = ''
access_stats_path = ''
openai_api_key = ''
openai_api_base = ''
openai_model = ''
VERBOSE = False
chroma_db_path = ''
db_path = ''
COOKIE_SECURE = False
COOKIE_MAX_AGE = 86400
RERANK_ENABLED = False
RERANK_RECALL_K = 10
RERANK_TOP_N = 5
RERANK_SCORE_THRESHOLD = 0.75
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
HYBRID_RETRIEVAL_ENABLED = True

# 检索 top_k 集中配置（Phase 2）。三处调用点历史上各自硬编码了不同的值，
# 业务含义并不相同，这里只是把"数字定义在哪"集中到一处、可通过环境变量覆盖，
# 默认值和改造前完全一致，不改变现有线上行为：
# - DEFAULT_SIMILARITY_TOP_K：主查询路径（单索引直接查询 / RouterQueryEngine
#   多索引路由，backend/app/handlers/graph_builder.py 的 _build_query_engine）
#   用的默认值，也是新代码没有特殊理由时应该用的默认值。原值 5。
# - QUERY_ENDPOINT_TOP_K：backend/app/router/index.py 的 /query 接口历史上就
#   故意用更小的 top_k（更快但召回更少），这是有意的行为差异，不是遗漏，
#   保留不变。原值 2。
# - MULTI_INDEX_FALLBACK_TOP_K：MultiIndexQueryEngine（挨个查所有索引、取第
#   一个非空响应，backend/app/router/graph.py 的 /agent 路径用）的默认值。
#   原值 3。
DEFAULT_SIMILARITY_TOP_K = 5
QUERY_ENDPOINT_TOP_K = 2
MULTI_INDEX_FALLBACK_TOP_K = 3

# Rerank 配置（Phase 3.2 条件触发 + 轻量候选）。
# 默认关，不改变现有线上行为；打开后仅在向量检索 top1 分数低于阈值时才触发 rerank。
RERANK_ENABLED = False
RERANK_RECALL_K = 10
RERANK_TOP_N = 5
RERANK_SCORE_THRESHOLD = 0.75
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def reload_env_variables():
    load_dotenv(os.path.join(os.path.dirname(PROJECT_ROOT), '.env'), override=True)
    global index_save_directory, SAVE_PATH, LOAD_PATH, FEEDBACK_PATH, LOG_PATH, FILE_PATH, access_stats_path, \
        openai_api_key, openai_api_base, openai_model, VERBOSE, COOKIE_SECURE, COOKIE_MAX_AGE, chroma_db_path, \
        db_path, DEFAULT_SIMILARITY_TOP_K, QUERY_ENDPOINT_TOP_K, MULTI_INDEX_FALLBACK_TOP_K, \
        RERANK_ENABLED, RERANK_RECALL_K, RERANK_TOP_N, RERANK_SCORE_THRESHOLD, RERANKER_MODEL, \
        HYBRID_RETRIEVAL_ENABLED

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    openai_api_base = os.environ.get('OPENAI_API_BASE') or 'https://api.openai.com/v1'
    openai_model = os.environ.get('OPENAI_MODEL', 'sensenova-6.7-flash-lite')
    VERBOSE = os.environ.get('VERBOSE', 'False').lower() in ('true', '1', 't')

    index_save_directory = os.environ.get('INDEX_SAVE_DIRECTORY', '../../data/indexes/')
    SAVE_PATH = os.environ.get('SAVE_PATH', '../../data/upload_files')
    LOAD_PATH = os.environ.get('LOAD_PATH', '../../data/temp/')
    FEEDBACK_PATH = os.environ.get('FEEDBACK_PATH', '../../feedback/')
    LOG_PATH = os.environ.get('LOG_PATH', '../../log/')
    FILE_PATH = os.environ.get('FILE_PATH', '../../data/export/')
    chroma_db_path = os.environ.get('CHROMA_DB_PATH', '../../data/chroma_db/')
    db_path = os.environ.get('DB_PATH', '../../data/app.db')

    index_save_directory = os.path.join(PROJECT_ROOT, index_save_directory)
    SAVE_PATH = os.path.join(PROJECT_ROOT, SAVE_PATH)
    LOAD_PATH = os.path.join(PROJECT_ROOT, LOAD_PATH)
    FEEDBACK_PATH = os.path.join(PROJECT_ROOT, FEEDBACK_PATH)
    LOG_PATH = os.path.join(PROJECT_ROOT, LOG_PATH)
    FILE_PATH = os.path.join(PROJECT_ROOT, FILE_PATH)
    chroma_db_path = os.path.join(PROJECT_ROOT, chroma_db_path)
    db_path = os.path.join(PROJECT_ROOT, db_path)
    access_stats_path = os.path.join(PROJECT_ROOT, '../access_stats.json')

    COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'False').lower() in ('true', '1', 't')
    COOKIE_MAX_AGE = int(os.environ.get('COOKIE_MAX_AGE', '86400'))

    DEFAULT_SIMILARITY_TOP_K = int(os.environ.get('SIMILARITY_TOP_K', '5'))
    QUERY_ENDPOINT_TOP_K = int(os.environ.get('QUERY_ENDPOINT_TOP_K', '2'))
    MULTI_INDEX_FALLBACK_TOP_K = int(os.environ.get('MULTI_INDEX_FALLBACK_TOP_K', '3'))

    global RERANK_ENABLED, RERANK_RECALL_K, RERANK_TOP_N, RERANK_SCORE_THRESHOLD, RERANKER_MODEL
    RERANK_ENABLED = os.environ.get('RERANK_ENABLED', 'False').lower() in ('true', '1', 't')
    RERANK_RECALL_K = int(os.environ.get('RERANK_RECALL_K', '10'))
    RERANK_TOP_N = int(os.environ.get('RERANK_TOP_N', '5'))
    RERANK_SCORE_THRESHOLD = float(os.environ.get('RERANK_SCORE_THRESHOLD', '0.75'))
    RERANKER_MODEL = os.environ.get('RERANKER_MODEL', 'BAAI/bge-reranker-v2-m3')

    # 混合检索（BM25+dense RRF 融合，见 handlers/hybrid_retriever.py）。
    # evals/run_hybrid_eval.py 在 campus-corpus 上验证过收益（20 题：
    # hit@1 75%->85%、MRR 0.852->0.896，延迟只多约 2ms），默认开启。
    HYBRID_RETRIEVAL_ENABLED = os.environ.get('HYBRID_RETRIEVAL_ENABLED', 'True').lower() in ('true', '1', 't')

    # 启动时校验必需的 env 变量
    if not openai_api_key:
        logging.warning("OPENAI_API_KEY is not set. LLM queries will fail until configured.")


MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md', '.csv', '.xlsx'}

reload_env_variables()
