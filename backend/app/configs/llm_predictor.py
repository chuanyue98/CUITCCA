from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.openai_like import OpenAILike
import torch

import configs.load_env as env_config

# SenseNova (https://token.sensenova.cn/v1/models) 免费模型的上下文窗口大小；
# llama_index 的 OpenAI() 会校验模型名是否在其内置 OpenAI 模型白名单里，
# 第三方 OpenAI 兼容服务的模型名不在该白名单中，因此这里改用 OpenAILike，
# 显式声明 is_chat_model/context_window 以绕过白名单校验。
_CONTEXT_WINDOWS = {
    'sensenova-6.7-flash-lite': 262144,
    'deepseek-v4-flash': 1048576,
    'glm-5.2': 1048576,
    'sensenova-u1-fast': 262144,
}
_DEFAULT_CONTEXT_WINDOW = 32768
_MAX_TOKENS = 4096


def build_llm() -> OpenAILike:
    """
    每次调用都读取 configs.load_env 的当前值（而不是在模块导入时固定下来），
    这样 /manage/env 更新密钥/模型后，重新调用本函数即可生效。
    """
    model = env_config.openai_model
    return OpenAILike(
        model=model,
        api_key=env_config.openai_api_key,
        api_base=env_config.openai_api_base,
        is_chat_model=True,
        context_window=_CONTEXT_WINDOWS.get(model, _DEFAULT_WINDOW := _DEFAULT_CONTEXT_WINDOW),
        max_tokens=_MAX_TOKENS,
    )


def init_settings():
    """Lazily initialize settings to avoid immediate loading of models on import."""
    if Settings.embed_model is None or not isinstance(Settings.embed_model, HuggingFaceEmbedding):
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        Settings.embed_model = HuggingFaceEmbedding(
            model_name="DMetaSoul/Dmeta-embedding-zh-small",
            device=device,
            normalize=True,
        )
    if Settings.llm is None or not isinstance(Settings.llm, OpenAILike):
        Settings.llm = build_llm()
    if Settings.text_splitter is None:
        Settings.text_splitter = SentenceSplitter.from_defaults(chunk_size=512)


if __name__ == '__main__':
    init_settings()
    print(Settings.llm.complete('hi'))

