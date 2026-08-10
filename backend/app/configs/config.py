from enum import Enum

from llama_index.core import PromptTemplate


class ResponseMode(str, Enum):
    """响应生成器（和合成器）的响应模式。"""
    COMPACT = "compact"
    """
    Compact 和 refine 模式首先将文本块组合成较大的合并块，以更充分地利用 \
    可用的上下文窗口，然后在其中细化答案。这种模式比 refine 更快，因为我们对 \
    LLM 进行的调用更少。
    """

    REFINE = "refine"
    """
    Refine 是一种迭代生成响应的方式。我们首先使用第一个节点中的上下文，以及查询，\
    生成一个初始答案。然后，我们将这个答案、查询和第二个节点的上下文作为输入，\
    传递到"refine prompt"中生成一个更精细的答案。我们通过 N-1 个节点进行细化，\
    其中 N 是节点的总数。
    """

    SIMPLE_SUMMARIZE = "simple_summarize"
    """
    将所有文本块合并成一个，然后进行 LLM 调用。如果合并后的文本块超过上下文窗口大小，\
    则此操作将失败。
    """

    TREE_SUMMARIZE = "tree_summarize"
    """
    在候选节点集上建立树索引，使用查询作为汇总提示。树是自下而上构建的，最后\
    返回根节点作为响应。
    """

    GENERATION = "generation"
    """忽略上下文，只使用 LLM 生成响应。"""

    NO_TEXT = "no_text"
    """返回检索到的上下文节点，而不合成最终响应。"""

    ACCUMULATE = "accumulate"
    """为每个文本块综合生成一个响应，然后返回连接的结果。"""

    COMPACT_ACCUMULATE = "compact_accumulate"
    """
    Compact 和 accumulate 模式首先将文本块组合成较大的合并块，以更充分地利用 \
    可用的上下文窗口，然后为每个块综合生成一个响应，最后返回连接的结果。这种模式比 \
    accumulate 更快，因为我们对 LLM 进行的调用更少。
    """


class PromptType(str, Enum):
    """使用 QA 提示生成答案。"""
    QA_PROMPT = 'QA_PROMPT'
    """使用 condense_question_prompt 提示生成答案。"""
    CONDENSE_QUESTION_PROMPT = 'CONDENSE_QUESTION_PROMPT'


class Prompts(Enum):
    QA_PROMPT = PromptTemplate(
        "你是成都信息工程大学校园小助手，仅回答学校有关的问题，其他问题都不回答\n"
        "我们已提供以下上下文信息。 \n"
        "---------------------\n"
        "{context_str}"
        "\n---------------------\n"
        "根据这些信息，请回答问题：{query_str}\n"
    )
    CONDENSE_QUESTION_PROMPT = PromptTemplate(
        "给定一段人类用户与AI助手之间的对话历史和人类用户的后续留言, "
        "将消息改写成一个独立问题仅补充后续留言不改变后续留言意思。"
        "<Chat History> {chat_history} "
        "<Follow Up Message> {question} "
        "<Standalone question>"
    )
    REFINE_PROMPT = PromptTemplate(
        "原始问题如下: {query_str} "
        "我们已经提供了一个现有的答案: {existing_answer} "
        "我们有机会通过下面的一些更多上下文来完善现有的答案（仅在需要时）。"
        "{context_msg} "
        "利用新的上下文和您自己的知识，更新或重复现有的答案,"
        "如果答案与问题不符，请直接回答我不知道。"
    )
    QUERY_REWRITE_PROMPT = PromptTemplate(
        "你是检索查询改写专家。把用户问题改写成一个更适合在校园知识库中检索的"
        "查询，目标是让检索结果更准确地命中问题真正想找的内容。改写要求：\n"
        "1. 保留原问题要问的核心事实，不要改变语义、不要添加问题里没有的信息。\n"
        "2. 补充同义词、全称（缩写展开）、常见表述变体，方便关键词检索命中\n"
        "   （比如\"校训\"可补\"成于大气 信达天下\"；\"图书馆\"可补\"借阅\"）。\n"
        "3. 如果原问题包含口语化/模糊表达，改写得更正式、更具体。\n"
        "4. 只输出改写后的查询本身，不要任何解释、不要引号。\n"
        "<Original Question> {query_str} \n"
        "<Rewritten Query>"
    )
    """条件触发查询改写（``handlers/qa_workflow.py`` 的 ``retrieve`` step）用的
    模板：检索结果置信度低（top1 分数 < ``QUERY_REWRITE_SCORE_THRESHOLD``）时，
    让 LLM 把原始问题改写得更适合检索再查一次。和 ``CONDENSE_QUESTION_PROMPT``
    的区别：condense 是"多轮追问 -> 独立问题"（有对话历史才触发），这里是一
    轮内"问题 -> 更好的检索词"（单轮低置信度就触发），语义不同所以单独一个模板。"""
    AGENT_SYSTEM_PROMPT = PromptTemplate(
        "你是成都信息工程大学校园小助手（Agent 模式），可以自主调用工具查阅"
        "校园知识库，而不是凭空回答。\n"
        "规则：\n"
        "1. 仅回答与学校有关的问题，其它问题礼貌拒绝，不要调用工具浪费轮次。\n"
        "2. 回答必须基于工具检索到的内容；工具没查到相关信息时，直接如实说"
        "\"我还不知道，请反馈给我吧\"，不要编造。\n"
        "3. 不确定该查哪个知识库时，可以先调用列出知识库的工具看看有哪些索引，"
        "再决定检索哪一个或不指定索引让系统自动选择。\n"
        "4. 第一次检索结果不够回答问题时，可以换一个关键词或指定的知识库再检索"
        "一次，而不是立刻放弃；但同一个问题不要无意义地反复检索。\n"
        "5. 最终回答里，尽量指出信息来自哪个文档（file_name 或 source_url），"
        "方便用户核实。\n"
        "6. 工具调用次数是有限的，达到上限时用已经查到的信息给出当前能给出的"
        "最好回答，并说明哪些部分还不确定，不要假装已经查得很全面。"
    )
    """Agent 模式（``agents/agent_workflow.py``）用的 system prompt。跟
    ``QA_PROMPT`` 分开是因为 QA_PROMPT 是"给定上下文回答"的单轮模板（用
    ``{context_str}``/``{query_str}`` 做字符串替换），而这里是驱动
    ``FunctionAgent`` 多轮工具调用决策的系统提示，语义不同、不应该合并成一个
    模板复用两种用途。"""


if __name__ == '__main__':
    print(Prompts.QA_PROMPT)
