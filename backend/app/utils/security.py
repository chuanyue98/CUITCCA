import os
import secrets

from fastapi import HTTPException, status
from starlette.requests import Request


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
    if not auth.startswith('Bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    provided_key = auth.removeprefix('Bearer ')
    if not secrets.compare_digest(provided_key, api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
