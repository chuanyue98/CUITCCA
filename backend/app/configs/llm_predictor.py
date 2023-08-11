from enum import Enum

from langchain.chat_models import ChatOpenAI
from llama_index import LLMPredictor

from configs import openai_api_key


class LLMPredictorOption(Enum):
    DEFAULT = LLMPredictor(
        llm=ChatOpenAI(openai_api_key=openai_api_key)
    )
    """GPT3.5"""
    GPT3_5 = LLMPredictor(
        llm=ChatOpenAI(temperature=0.1, model_name="gpt-3.5-turbo-16k", max_tokens=1024,
                       openai_api_key=openai_api_key)
    )


if __name__ == '__main__':
    llm_predictor = LLMPredictorOption.GPT3_5.value

