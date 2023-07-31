from fastapi import APIRouter, Depends, Form
from llama_index import get_response_synthesizer

from app.configs.config import ResponseMode,PromptType
from app.dependencies import get_index
from app.handlers.handler import get_prompt_by_name

response_app = APIRouter()

@response_app.post("/{index_name}/query")
async def query_index(response_mode: ResponseMode, prompt_type: PromptType, query: str = Form(), index=Depends(get_index)):
    response_synthesizer = get_response_synthesizer(response_mode=response_mode)
    prompt = get_prompt_by_name(prompt_type)
    engine = index.as_query_engine(refine_tempalate=prompt,response_synthesizer=response_synthesizer)
    return await engine.aquery(query)

