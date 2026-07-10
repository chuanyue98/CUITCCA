from pydantic import BaseModel
from typing import List, Optional, Any


class IndexListResponse(BaseModel):
    indexes: List[str]


class QueryResponse(BaseModel):
    response: str


class SourceNode(BaseModel):
    id: str
    text: str
    score: Optional[float] = None


class QuerySourcesResponse(BaseModel):
    source_nodes: List[SourceNode]


class UploadResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    status: str = "detail"
    message: str


class StatsResponse(BaseModel):
    total_visits: int
    ip_count: int
    user_visits: dict
    endpoint_visits: dict


class FeedbackResponse(BaseModel):
    message: str


class EnvUpdateResponse(BaseModel):
    message: str
