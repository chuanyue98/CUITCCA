import asyncio
import os

import configs.load_env as load_env
from dependencies.manage import access_stats, access_stats_lock
from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException
from models.llm_config import (
    LLMConfigResponse,
    LLMConfigUpdate,
    LLMProbeRequest,
    LLMProbeResponse,
)
from models.response import FeedbackListResponse, FeedbackResponse, StatsResponse
from models.user import Feedback
from starlette.requests import Request
from utils import llm_config
from utils.file import save_feedback
from utils.security import get_client_ip, require_configured_api_key

manage_app = APIRouter()


@manage_app.get("/stats", response_model=StatsResponse, dependencies=[Depends(require_configured_api_key)])
async def get_stats():
    """获取访问统计"""
    async with access_stats_lock:
        return StatsResponse(
            total_visits=access_stats["total_visits"],
            ip_count=access_stats["ip_count"],
            user_visits=dict(access_stats["user_visits"]),
            endpoint_visits=dict(access_stats["endpoint_visits"]),
        )


@manage_app.post("/feedback", response_model=FeedbackResponse, dependencies=[Depends(require_configured_api_key)])
async def create_feedback(feedback: Feedback, request: Request):
    """创建反馈"""
    client_ip = get_client_ip(request)
    await save_feedback(client_ip, feedback)
    return FeedbackResponse(message="Feedback received")


@manage_app.get("/feedback", response_model=FeedbackListResponse, dependencies=[Depends(require_configured_api_key)])
async def get_feedback(limit: int = 100):
    """列出最近的用户反馈"""
    from utils import db
    entries = await asyncio.to_thread(db.list_feedback, load_env.db_path, limit)
    return FeedbackListResponse(feedback=entries)


_env_path = llm_config.ENV_PATH


@manage_app.get('/env', dependencies=[Depends(require_configured_api_key)])
async def get_env():
    """只读脱敏返回当前环境变量配置，不再支持通过接口修改。

    修改 LLM 配置请直接编辑 .env 文件后重启服务（或用 /llm-config 接口，
    那是 POST /env 的收敛版：只允许改 LLM 三项）。原来通过 POST /env
    任意修改环境变量的能力存在安全风险，已移除。
    """
    env_values = dotenv_values(_env_path)

    masked_file = {
        'OPENAI_API_KEY': llm_config.mask_key(env_values.get('OPENAI_API_KEY', '')),
        'OPENAI_API_BASE': env_values.get('OPENAI_API_BASE', ''),
        'OPENAI_MODEL': env_values.get('OPENAI_MODEL', ''),
    }
    runtime = {
        'OPENAI_API_KEY': llm_config.mask_key(os.environ.get('OPENAI_API_KEY', '')),
        'OPENAI_API_BASE': os.environ.get('OPENAI_API_BASE', ''),
        'OPENAI_MODEL': os.environ.get('OPENAI_MODEL', ''),
    }
    return {'status': 'ok', 'env_file': masked_file, 'runtime': runtime}


@manage_app.get('/llm-config', response_model=LLMConfigResponse, dependencies=[Depends(require_configured_api_key)])
async def get_llm_config():
    """当前生效的 LLM 连接配置，key 脱敏。"""
    return llm_config.read_llm_config()


@manage_app.post('/llm-config', response_model=LLMConfigResponse, dependencies=[Depends(require_configured_api_key)])
async def update_llm_config(payload: LLMConfigUpdate):
    """更新 LLM 配置：写 .env 并热生效（重建 Settings.llm），无需重启。

    api_key 留空表示保留现有 key——前端回显的是脱敏值，不能拿它覆盖真值。
    空 base/model 和非法 scheme 由 Pydantic 模型校验（models/llm_config.py），
    这里只处理 IO 和热生效两阶段的失败语义。
    """
    try:
        result = await asyncio.to_thread(
            llm_config.write_llm_config,
            payload.api_base,
            payload.model,
            (payload.api_key or '').strip() or None,
        )
    except llm_config.InvalidLLMConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f'写入 .env 失败: {exc}')
    except Exception as exc:
        # 走到这里说明文件已落盘、_apply_runtime 重建 Settings.llm 失败
        # （如第三方网关连不上）：不是"写入失败"，重启后配置仍会生效。
        raise HTTPException(status_code=500, detail=f'配置已写入 .env，但热生效失败（重启服务后生效）: {exc}')
    return result


@manage_app.post('/llm-probe', response_model=LLMProbeResponse, dependencies=[Depends(require_configured_api_key)])
async def probe_llm_endpoint(payload: LLMProbeRequest):
    """探测 OpenAI 兼容端点连通性并返回可用模型列表。

    api_key 留空时用当前已配置的 key。注意这是服务端代请求（SSRF 面），
    与其他管理接口一样仅对持有 CUITCCA_API_KEY 的管理员开放。
    """
    result = await asyncio.to_thread(
        llm_config.probe_endpoint,
        payload.api_base.strip(),
        (payload.api_key or '').strip() or None,
    )
    return result
