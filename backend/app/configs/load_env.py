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
#
# 阈值 0.45 是拿真实评测数据校准过的：campus-corpus 76 题里 59 道 top1 命中的
# 分数范围 0.407~0.748、均值 0.546，如果用 0.6 会把 76% 的正常查询也拖进第二次
# 检索（违背"高置信度零额外开销"的承诺）；降到 0.45 后只有 ~7%（4/59）的命中
# 查询会触发。注意分数阈值只能抓住"检索确实没把握"这一类失败（比如 q069 的
# 0.42），抓不住"分数不低但召回了错误文档"（比如 q038 的 0.55）——后者是标题
# 强匹配挤掉正确文档，需要的是文档级去重或 metadata 过滤，不是查询改写。
QUERY_REWRITE_ENABLED = True
QUERY_REWRITE_SCORE_THRESHOLD = 0.45

# 语义缓存 / 人工问答沉淀（handlers/qa_cache.py）：相同/相似问题命中缓存时
# 直接复用历史答案，跳过检索 + LLM 生成（生产环境省成本、降延迟的标配）。
# 存储是独立的 Chroma collection（cosine 空间），分两种 kind，命中阈值不同：
# - auto（每次成功问答自动写入，未经人工校验）：阈值 0.92，只有几乎逐字
#   相同的问题才敢直接复用——自动条目的答案没被人背过书，宁可miss也不给错。
# - curated（👍 人工沉淀，Dify annotation reply 同款机制）：阈值 0.82，允许
#   一定程度的同义改写复用——人背过书的高价值问答，措辞不同但意思一样就该
#   命中。
# 缓存查找只花一次本地 bge-m3 嵌入（毫秒级），miss 时多花的这点成本远低于
# 命中时省下的整次检索 + LLM 生成。QA_CACHE_MAX_AUTO_ENTRIES 上限只驱逐 auto
# 条目（按命中次数升序），curated 是人工资产不驱逐。
QA_CACHE_ENABLED = True
QA_CACHE_COLLECTION = "qa_cache"
QA_CACHE_AUTO_THRESHOLD = 0.92
QA_CACHE_CURATED_THRESHOLD = 0.82
QA_CACHE_MAX_AUTO_ENTRIES = 500

# 自动路由（handlers/auto_router.py）：去掉用户可见的"标准问答/Agent 模式"
# 切换器后，用这个阈值判断一次提问该走零决策开销的 QAWorkflow 还是会多跳
# 检索的 FunctionAgent。判据是**重排后**的 cross-encoder top1 分数，不是
# RRF 融合分数——campus-corpus 上实测过两类问题的分数分布：
#   RRF 融合 top1：语料覆盖的问题 0.026~0.033，语料未覆盖的问题同样是
#   0.026~0.033，两类问题的分数几乎完全重叠，没有任何区分度，不能拿它做
#   判断依据。
#   重排后 top1：语料覆盖的问题 0.7286/0.9862/0.9863，语料未覆盖的问题
#   0.0097/0.0285/0.1565/0.4950——区分度很好。
# 0.6 取在覆盖侧实测最低值 0.73 和未覆盖侧实测最高值 0.50 中间，两边都留了
# 安全余量。前提是 RERANK_ENABLED=True（重排真的发生了、分数有区分度）；
# 关闭时 auto_router 只用"检索是否为空"这一个信号路由，不会拿没有区分度的
# RRF 分数比这个阈值，见 handlers/auto_router.py 模块 docstring。
AUTO_ROUTE_SCORE_THRESHOLD = 0.6

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

# 摄取管道的噪声块过滤阈值（handlers/ingestion_pipeline.py:NoiseNodeFilter）。
# 实测 campus 索引 1537 个 chunk 里 42 个（2.7%）纯空白、38 个（2.5%）内容只剩
# "扫描全能王 创建" 这类 OCR 软件水印、62 个（4.0%）不足 30 字的碎片（比如
# "7\n7"、"利结业 次"）——这些块照样被向量化、参与召回，纯粹是检索噪声。
# 30 是经验值：短于这个长度的中文文本基本不可能承载一个完整、可检索的语义
# 单元（差不多是一句短话的长度），可通过 MIN_CHUNK_LENGTH 按语料实际情况调整。
MIN_CHUNK_LENGTH = 30


def reload_env_variables():
    load_dotenv(os.path.join(os.path.dirname(PROJECT_ROOT), '.env'), override=True)
    global index_save_directory, SAVE_PATH, LOAD_PATH, FEEDBACK_PATH, LOG_PATH, FILE_PATH, access_stats_path, \
        openai_api_key, openai_api_base, openai_model, VERBOSE, COOKIE_SECURE, COOKIE_MAX_AGE, chroma_db_path, \
        db_path, DEFAULT_SIMILARITY_TOP_K, QUERY_ENDPOINT_TOP_K, MULTI_INDEX_FALLBACK_TOP_K, \
        RERANK_ENABLED, RERANK_RECALL_K, RERANK_TOP_N, RERANK_SCORE_THRESHOLD, RERANKER_MODEL, \
        HYBRID_RETRIEVAL_ENABLED, QUERY_REWRITE_ENABLED, QUERY_REWRITE_SCORE_THRESHOLD, \
        AUTO_ROUTE_SCORE_THRESHOLD, QA_CACHE_ENABLED, QA_CACHE_COLLECTION, QA_CACHE_AUTO_THRESHOLD, \
        QA_CACHE_CURATED_THRESHOLD, QA_CACHE_MAX_AUTO_ENTRIES, MIN_CHUNK_LENGTH

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
    # 低延迟承诺。阈值取值依据见上方模块级常量注释（0.45 由真实评测数据校准）。
    QUERY_REWRITE_ENABLED = os.environ.get('QUERY_REWRITE_ENABLED', 'True').lower() in ('true', '1', 't')
    QUERY_REWRITE_SCORE_THRESHOLD = float(os.environ.get('QUERY_REWRITE_SCORE_THRESHOLD', '0.45'))

    # 自动路由阈值。校准依据见上方模块级常量注释（campus-corpus 实测的
    # RRF vs 重排分数对比）。
    AUTO_ROUTE_SCORE_THRESHOLD = float(os.environ.get('AUTO_ROUTE_SCORE_THRESHOLD', '0.6'))

    # 语义缓存。默认开启（本地嵌入毫秒级成本），相关说明见上方模块级常量注释。
    QA_CACHE_ENABLED = os.environ.get('QA_CACHE_ENABLED', 'True').lower() in ('true', '1', 't')
    QA_CACHE_COLLECTION = os.environ.get('QA_CACHE_COLLECTION', 'qa_cache')
    QA_CACHE_AUTO_THRESHOLD = float(os.environ.get('QA_CACHE_AUTO_THRESHOLD', '0.92'))
    QA_CACHE_CURATED_THRESHOLD = float(os.environ.get('QA_CACHE_CURATED_THRESHOLD', '0.82'))
    QA_CACHE_MAX_AUTO_ENTRIES = int(os.environ.get('QA_CACHE_MAX_AUTO_ENTRIES', '500'))

    # 摄取管道噪声块过滤的最小保留长度。校准依据见上方模块级常量注释。
    MIN_CHUNK_LENGTH = int(os.environ.get('MIN_CHUNK_LENGTH', '30'))

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
