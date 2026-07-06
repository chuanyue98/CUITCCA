import os

from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    校验 Authorization: Bearer <api_key>。

    注意：这里必须返回 JSONResponse 而不是 raise HTTPException——在
    BaseHTTPMiddleware.dispatch 里抛出 HTTPException 不会被 FastAPI 的异常处理器
    捕获，会直接变成裸的 500，而不是预期的 401（已用最小复现验证过）。
    """

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer ') or auth.removeprefix('Bearer ') != self.api_key:
            return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Unauthorized"})
        return await call_next(request)


def require_configured_api_key(request: Request) -> None:
    """
    要求调用方在 Authorization 头中提供与 CUITCCA_API_KEY 匹配的 Bearer token。
    若服务端未配置 CUITCCA_API_KEY，则该接口视为不可用（而不是无条件放行），
    防止在默认（未配置密钥）部署下被任意调用者滥用。
    """
    api_key = os.environ.get('CUITCCA_API_KEY', '')
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="此接口需要先配置 CUITCCA_API_KEY 才能使用",
        )
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer ') or auth.removeprefix('Bearer ') != api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
