
from pydantic import BaseModel


class IndexListResponse(BaseModel):
    indexes: list[str]


class QueryResponse(BaseModel):
    response: str


class SourceNode(BaseModel):
    id: str
    text: str
    score: float | None = None
    file_name: str | None = None
    """来源节点所属的源文件名（metadata.file_name）。前端引用来源列表可以
    直接展示"这份内容来自哪个文件"，不用再猜。检索/QA 路径的 node metadata
    里都有这个字段（documents_from_file 写入），缺失时是 None 也不影响。"""


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
