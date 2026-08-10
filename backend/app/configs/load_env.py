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
RERANK_ENABLED = True
RERANK_RECALL_K = 20
RERANK_TOP_N = 5
RERANK_SCORE_THRESHOLD = 0.75
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
HYBRID_RETRIEVAL_ENABLED = True

# 条件触发查询改写（handlers/qa_workflow.py 的 retrieve step）：检索结果 top1
# 分数低于 QUERY_REWRITE_SCORE_THRESHOLD 时，用 LLM 把原始问题改写得更适合
# 检索再查一次。跟 RERANK 的触发思路一样（低置信度才付出额外成本），但改写
# 解决的是另一类问题——rerank 只能在"已经召回的内容里"排序，如果正确文档
# 因为措辞/术语不匹配压根没进召回（比如评测里 q038/q069 的"标题关键词强匹配
# 挤掉正确答案"），rerank 帮不上忙，改写查询让第二次检索有机会召回它。
QUERY_REWRITE_ENABLED = True
QUERY_REWRITE_SCORE_THRESHOLD = 0.6

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

# Rerank 配置（Phase 3.2 条件触发 + 轻量候选；Phase C 默认转正）。
# 仅在向量/混合检索 top1 分数低于阈值时才触发 rerank。RERANK_RECALL_K=20 是
# evals/run_rerank_eval.py 和 run_hybrid_eval.py 的 C 组实际验证过的召回量
# （campus-corpus 20 题：hit@1 75%->90%、MRR 0.852->0.910），不是拍脑袋的数字，
# 不要在没有新评测数据支撑的情况下改回 10。
RERANK_ENABLED = True
RERANK_RECALL_K = 20
RERANK_TOP_N = 5
RERANK_SCORE_THRESHOLD = 0.75
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def reload_env_variables():
    load_dotenv(os.path.join(os.path.dirname(PROJECT_ROOT), '.env'), override=True)
    global index_save_directory, SAVE_PATH, LOAD_PATH, FEEDBACK_PATH, LOG_PATH, FILE_PATH, access_stats_path, \
        openai_api_key, openai_api_base, openai_model, VERBOSE, COOKIE_SECURE, COOKIE_MAX_AGE, chroma_db_path, \
        db_path, DEFAULT_SIMILARITY_TOP_K, QUERY_ENDPOINT_TOP_K, MULTI_INDEX_FALLBACK_TOP_K, \
        RERANK_ENABLED, RERANK_RECALL_K, RERANK_TOP_N, RERANK_SCORE_THRESHOLD, RERANKER_MODEL, \
        HYBRID_RETRIEVAL_ENABLED, QUERY_REWRITE_ENABLED, QUERY_REWRITE_SCORE_THRESHOLD

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
    RERANK_ENABLED = os.environ.get('RERANK_ENABLED', 'True').lower() in ('true', '1', 't')
    RERANK_RECALL_K = int(os.environ.get('RERANK_RECALL_K', '20'))
    RERANK_TOP_N = int(os.environ.get('RERANK_TOP_N', '5'))
    RERANK_SCORE_THRESHOLD = float(os.environ.get('RERANK_SCORE_THRESHOLD', '0.75'))
    RERANKER_MODEL = os.environ.get('RERANKER_MODEL', 'BAAI/bge-reranker-v2-m3')

    # 混合检索（BM25+dense RRF 融合，见 handlers/hybrid_retriever.py）。
    # evals/run_hybrid_eval.py 在 campus-corpus 上验证过收益（20 题：
    # hit@1 75%->85%、MRR 0.852->0.896，延迟只多约 2ms），默认开启。
    HYBRID_RETRIEVAL_ENABLED = os.environ.get('HYBRID_RETRIEVAL_ENABLED', 'True').lower() in ('true', '1', 't')

    # 条件触发查询改写。默认开启：只在检索 top1 置信度低时付出一次 LLM 改写
    # 调用的成本，高置信度（>= 阈值）时零额外开销，不影响单轮问答主路径的
    # 低延迟承诺。
    QUERY_REWRITE_ENABLED = os.environ.get('QUERY_REWRITE_ENABLED', 'True').lower() in ('true', '1', 't')
    QUERY_REWRITE_SCORE_THRESHOLD = float(os.environ.get('QUERY_REWRITE_SCORE_THRESHOLD', '0.6'))

    # 启动时校验必需的 env 变量
    if not openai_api_key:
        logging.warning("OPENAI_API_KEY is not set. LLM queries will fail until configured.")


MAX_FILE_SIZE = 10 * 1024 * 1024

# 上传白名单。原来只有 6 种格式（pdf/docx/txt/md/csv/xlsx），实测语料目录
# 257 个文件里有 54 个（21%）因此被挡在门外且**毫无提示**——17 个 .doc、
# 2 个 .xls、2 个 .pptx、4 个流程图 .jpg，其中不少是"休学/复学流程""就业
# 负责人联系方式"这类高频问题的唯一来源。handlers/parsers 注册表补齐了这些
# 格式的解析能力后，白名单同步放开。
#
# 这里刻意**显式列举**而不是直接写成 parsers.supported_extensions()：白名单是
# 一道安全控制（决定服务器愿意接收什么文件），应当能一眼看清、单独审计，而
# 不是跟着解析器注册表的增减自动漂移——将来给注册表加一种格式，不应该顺带
# 就把它变成"任何人都能上传"。两者的一致性由 tests/test_upload_validation.py
# 的约束测试保证：白名单必须是注册表支持格式的子集（能收就必须能解析）。
#
# .json 刻意不加：语料目录里的 29 个 json 是旧版 llama_index 的持久化产物
# （docstore.json / vector_store.json 之类），不是知识内容。
ALLOWED_EXTENSIONS = {
    # 原有
    '.pdf', '.docx', '.txt', '.md', '.csv', '.xlsx',
    # 旧版 Office 二进制格式（OLE2）
    '.doc', '.xls',
    # 演示文稿
    '.pptx',
    # 网页（Web 连接器抓回来的页面走同一套解析）
    '.html', '.htm',
    # 图片走 OCR；OCR 是可选依赖（uv sync --extra ocr），未安装时解析器会
    # 明确返回"能力不可用"并提示安装方式，而不是静默产出空内容
    '.jpg', '.jpeg', '.png',
}

reload_env_variables()
