
from pydantic import BaseModel


class IndexListResponse(BaseModel):
    indexes: list[str]


class QueryResponse(BaseModel):
    response: str


class SourceNode(BaseModel):
    id: str
    text: str
    score: float | None = None


class QuerySourcesResponse(BaseModel):
    source_nodes: list[SourceNode]


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


class FeedbackEntry(BaseModel):
    created_at: str
    client_ip: str
    email: str | None = None
    message: str


class FeedbackListResponse(BaseModel):
    feedback: list[FeedbackEntry]
