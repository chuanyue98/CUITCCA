from configs.config import PromptType, ResponseMode
from dependencies import get_index
from fastapi import APIRouter, Depends, Form
from handlers.hybrid_retriever import build_retriever_for_index
from handlers.llama_handler import get_prompt_by_name
from handlers.qa_workflow import resolve_effective_top_k
from llama_index.core import get_response_synthesizer
from llama_index.core.query_engine import RetrieverQueryEngine
from models.response import QueryResponse
from utils.rerank import ConditionalRerankPostprocessor
from utils.security import require_api_key_if_configured

response_app = APIRouter(dependencies=[Depends(require_api_key_if_configured)])


@response_app.post("/{index_name}/query", response_model=QueryResponse)
async def query_index(
    response_mode: ResponseMode = Form(),
    prompt_type: PromptType = Form(),
    query: str = Form(),
    index=Depends(get_index),
):
    """按指定 response_mode / prompt_type 合成回答。

    检索走 ``build_retriever_for_index``——这是全项目检索构造的统一入口，混合
    检索（BM25+dense RRF）的开关判断和缓存都在它内部。这里以前直接调
    ``index.as_query_engine()``，等于**绕开了混合检索和条件重排**：同一个知识
    库、同一个问题，走 ``/graph`` 和走这个端点会得到不同质量的检索结果，而且
    差异完全不体现在任何配置里，排查起来很隐蔽。混合检索与 rerank 的收益都有
    评测数据支撑（见 evals/README.md），没有理由让这条链路单独退化成纯向量。

    召回宽度用 ``resolve_effective_top_k(None)`` 而不是直接写
    ``DEFAULT_SIMILARITY_TOP_K``：后者等于 ``RERANK_TOP_N``（都是 5），而
    ``ConditionalRerankPostprocessor`` 在 ``len(nodes) <= RERANK_TOP_N`` 时会
    直接跳过重排（候选数不够、没什么好排的）——只召回 5 条就挂一个永远不会
    触发的后处理器，纯粹是自欺欺人。``resolve_effective_top_k`` 在
    ``RERANK_ENABLED`` 打开时返回 ``RERANK_RECALL_K``（20），先宽召回、重排后
    再截断到 5，条件触发才真的有意义。这个坑 ``qa_workflow`` 里踩过并专门抽了
    这个函数出来复用，新调用点不该再各写一遍。

    顺带：宽召回对这个端点本身也是对的——它是给"想自己挑合成策略"的调用方
    用的，tree_summarize/accumulate 这类模式本来就需要更多候选节点才有意义。

    ``load_env.X`` 属性访问而不是 ``from ... import X``：后者在导入时就把值拷
    进本模块命名空间，``reload_env_variables()` 之后再也感知不到变化（项目里
    反复踩过的坑）。
    """
    retriever = build_retriever_for_index(index, resolve_effective_top_k(None))
    response_synthesizer = get_response_synthesizer(response_mode=response_mode)
    prompt = get_prompt_by_name(prompt_type)
    engine = RetrieverQueryEngine.from_args(
        retriever=retriever,
        refine_template=prompt,
        response_synthesizer=response_synthesizer,
        node_postprocessors=[ConditionalRerankPostprocessor()],
    )
    return QueryResponse(response=str(await engine.aquery(query)))

