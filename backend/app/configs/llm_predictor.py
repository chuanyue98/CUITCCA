from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.llms.openai_like import OpenAILike
import torch

import configs.load_env as env_config

_CONTEXT_WINDOWS = {
    'sensenova-6.7-flash-lite': 262144,
    'deepseek-v4-flash': 1048576,
    'glm-5.2': 1048576,
    'sensenova-u1-fast': 262144,
}
_DEFAULT_CONTEXT_WINDOW = 32768
_MAX_TOKENS = 4096


def build_llm() -> OpenAILike:
    model = env_config.openai_model
    return OpenAILike(
        model=model,
        api_key=env_config.openai_api_key,
        api_base=env_config.openai_api_base,
        is_chat_model=True,
        context_window=_CONTEXT_WINDOWS.get(model, _DEFAULT_CONTEXT_WINDOW),
        max_tokens=_MAX_TOKENS,
    )


def init_settings():
    if Settings._embed_model is None or not isinstance(Settings._embed_model, HuggingFaceEmbedding):
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        Settings.embed_model = HuggingFaceEmbedding(
            model_name="BAAI/bge-m3",
            device=device,
            normalize=True,
            trust_remote_code=True,
        )
    if Settings._llm is None or not isinstance(Settings._llm, OpenAILike):
        Settings.llm = build_llm()
    if Settings.text_splitter is None:
        Settings.text_splitter = SentenceSplitter.from_defaults(chunk_size=512)


if __name__ == '__main__':
    init_settings()
    print(Settings.llm.complete('hi'))

