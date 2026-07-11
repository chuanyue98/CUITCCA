from configs.config import PromptType, ResponseMode
from dependencies import get_index
from fastapi import APIRouter, Depends, Form
from handlers.llama_handler import get_prompt_by_name
from llama_index.core import get_response_synthesizer
from models.response import QueryResponse

response_app = APIRouter()


@response_app.post("/{index_name}/query", response_model=QueryResponse)
async def query_index(
    response_mode: ResponseMode = Form(),
    prompt_type: PromptType = Form(),
    query: str = Form(),
    index=Depends(get_index),
):
    response_synthesizer = get_response_synthesizer(response_mode=response_mode)
    prompt = get_prompt_by_name(prompt_type)
    engine = index.as_query_engine(refine_template=prompt, response_synthesizer=response_synthesizer)
    return QueryResponse(response=str(await engine.aquery(query)))

