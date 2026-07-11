import functools

from fastapi import HTTPException

from utils.logger import error_logger


def id_not_found_exceptions(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            error_message = str(e)
            error_logger.error(f"ValueError: {error_message}")
            raise HTTPException(status_code=404, detail="出错了，请换个方式提问吧，如再遇此问题，请联系管理员反馈")
    return wrapper
