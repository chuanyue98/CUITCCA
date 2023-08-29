from fastapi import HTTPException

from utils.logger import error_logger


def id_not_found_exceptions(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            error_message = str(e)
            extracted_doc_id = error_message.split("doc_id ")[1].split(" ")[0]
            error_logger.error("ValueError doc_id: " + extracted_doc_id)
            raise HTTPException(status_code=500, detail="出错了，请换个方式提问吧，如再遇此问题，请联系管理员反馈")
    return wrapper