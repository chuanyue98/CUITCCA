from typing import Optional, List, Mapping, Any

from langchain.embeddings import HuggingFaceEmbeddings
from llama_index import ServiceContext, SimpleDirectoryReader, SummaryIndex
from llama_index.callbacks import CallbackManager
from llama_index.embeddings import LangchainEmbedding
from llama_index.llms import (
    CustomLLM,
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
)
from llama_index.llms.base import llm_completion_callback


class SparkLLM(CustomLLM):
    context_window: int = 3900
    num_output: int = 256
    model_name: str = "spark"
    dummy_response: str = "My response"

    @property
    def metadata(self) -> LLMMetadata:
        """Get LLM metadata."""
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=self.model_name,
        )

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        return CompletionResponse(text=self.dummy_response)

    @llm_completion_callback()
    def stream_complete(
        self, prompt: str, **kwargs: Any
    ) -> CompletionResponseGen:
        response = ""
        for token in self.dummy_response:
            response += token
            yield CompletionResponse(text=response, delta=token)


# define our LLM
llm = SparkLLM()

res = llm.complete("How are you?")
print(res)
# embed_model = LangchainEmbedding(
#         HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"))
#
# service_context = ServiceContext.from_defaults(
#     llm=llm, embed_model=embed_model
# )
#
# # Load the your data
# documents = SimpleDirectoryReader("./data").load_data()
# index = SummaryIndex.from_documents(documents, service_context=service_context)
#
# # Query and print response
# query_engine = index.as_query_engine()
# response = query_engine.query("<query_text>")
# print(response)