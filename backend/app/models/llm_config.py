from typing import Annotated

from pydantic import AfterValidator, BaseModel


def _validate_api_base(value: str) -> str:
    """strip + 非空 + http(s) scheme：`not-a-url` 这类值存进 .env 会让
    所有 LLM 调用静默挂掉，在入口就挡掉。"""
    value = value.strip()
    if not value:
        raise ValueError('api_base 不能为空')
    if not value.startswith(('http://', 'https://')):
        raise ValueError('api_base 必须以 http:// 或 https:// 开头')
    return value


def _validate_model(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError('model 不能为空')
    return value


ApiBase = Annotated[str, AfterValidator(_validate_api_base)]
ModelName = Annotated[str, AfterValidator(_validate_model)]


class LLMConfigResponse(BaseModel):
    api_base: str
    model: str
    api_key_masked: str
    warning: str | None = None


class LLMConfigUpdate(BaseModel):
    api_base: ApiBase
    model: ModelName
    api_key: str | None = None
    """留空表示保留现有 key。前端回显的是脱敏值（****xxxx），不能拿来覆盖真值。"""


class LLMProbeRequest(BaseModel):
    api_base: ApiBase
    api_key: str | None = None
    """留空时探测使用当前已配置的 key。"""


class LLMProbeResponse(BaseModel):
    ok: bool
    models: list[str] = []
    latency_ms: int | None = None
    error: str | None = None
