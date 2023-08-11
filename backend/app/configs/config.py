from enum import Enum

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
    传递到“refine prompt”中生成一个更精细的答案。我们通过 N-1 个节点进行细化，\
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
    """
       使用 QA 提示生成答案。
    """
    QA_PROMPT = 'QA_PROMPT'
    """
        使用 condense_question_prompt 提示生成答案。
    """
    CONDENSE_QUESTION_PROMPT = 'CONDENSE_QUESTION_PROMPT'


class Prompts(str, Enum):
    QA_PROMPT = ("下面是有关内容\n" "---------------------\n"
                 "{context_str}" "\n---------------------\n"
                 "根据这些信息，请回答问题: {query_str}\n"
                 "如果问题中提到图片，回答的内容有url,请使用markdown格式输出图片"
                 "如果您不知道的话，请回答不知道")
    CONDENSE_QUESTION_PROMPT = ("""\
                            给定一段人类用户与AI助手之间的对话历史和人类用户的后续留言, \
                            将消息改写成一个独立问题，以捕捉对话中的所有相关上下文。\
                        
                            <Chat History> 
                            {chat_history}
                            
                            <Follow Up Message>
                            {question}
                        
                            <Standalone question>
                            """)
