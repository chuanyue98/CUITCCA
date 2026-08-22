"""LLM 连接配置（base_url / api_key / model）的读取、写入与连通性探测。

写入即生效：更新 .env 后调用 ``load_env.reload_env_variables()`` 刷新模块级
配置，再重建 ``Settings.llm``——进行中的请求继续用旧客户端跑完，新请求走
新配置，全程无需重启服务。这是当年被移除的 POST /env 的收敛版：只允许改
LLM 三项，且路由层强制 CUITCCA_API_KEY 鉴权（见 router/manage.py）。

API key 只以脱敏形式返回（****+后 4 位）；明文仅在保存时写入 .env。
"""

import logging
import os
import re
import time

import httpx
from configs.load_env import ENV_PATH  # noqa: F401  (模块属性供测试 patch)
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

_PROBE_TIMEOUT_SECONDS = 10.0

# 无需引号的"安全值"字符集：字母数字和常见 URL/路径/密钥符号。
_PLAIN_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:+-]+$")

# .env 行级重写时识别"KEY=值"行（兼容行首空白和 export 前缀）。
_ENV_LINE_KEY_RE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=')


class InvalidLLMConfigError(ValueError):
    """入参语义校验失败（如把脱敏占位值当成新 key 保存）。路由层映射为 422。"""


def _format_env_line(key: str, value: str) -> str:
    """简单值保持原样输出（避免对 PORT=8522 这类行做无谓的加引号扰动），
    含空格/#/引号等特殊字符的值用单引号包裹。"""
    if _PLAIN_VALUE_RE.match(value):
        return f'{key}={value}'
    return f"{key}='{value.replace(chr(39), chr(39) * 2)}'"


def mask_key(value: str | None) -> str:
    """API key 脱敏：只留最后 4 位，不超过 4 位的短 key 全遮。"""
    if not value:
        return ''
    if len(value) <= 4:
        return '****'
    return '****' + value[-4:]


def read_llm_config() -> dict:
    """当前生效的 LLM 连接配置（运行时值），key 脱敏。"""
    import configs.load_env as load_env

    return {
        'api_base': load_env.openai_api_base or '',
        'model': load_env.openai_model or '',
        'api_key_masked': mask_key(load_env.openai_api_key),
    }


def write_llm_config(api_base: str, model: str, api_key: str | None = None) -> dict:
    """把 LLM 配置写入 .env 并热生效，返回写后的脱敏配置。

    api_key 为空时保留现有 key 不动。写文件用"临时文件 + os.replace"
    保证不会出现写一半被读到的半截 .env。模型不在上下文窗口表时照常
    接受，但返回 warning 提示会按默认 32768 处理（第三方网关的模型名
    五花八门，不宜在这里硬卡死）。

    重写是**行级**的：只替换三个目标 KEY 行，注释、空行、空值键
    （``KEY=``）和其他变量逐字保留——python-dotenv 往返重写会把注释
    全部丢掉、把空值键整个删掉，管理员手工维护的 .env 会被悄悄毁掉。
    """
    if api_key and api_key.startswith('****'):
        raise InvalidLLMConfigError(
            'api_key 不能是脱敏占位值（****xxxx），请输入完整 key 或留空保留现有 key'
        )

    updates = {
        'OPENAI_API_BASE': api_base,
        'OPENAI_MODEL': model,
    }
    if api_key:
        updates['OPENAI_API_KEY'] = api_key

    with open(ENV_PATH, encoding='utf-8') as f:
        lines = f.read().splitlines()

    replaced: set[str] = set()
    out_lines = []
    for line in lines:
        match = _ENV_LINE_KEY_RE.match(line)
        key = match.group(1) if match else None
        if key in updates:
            out_lines.append(_format_env_line(key, updates[key]))
            replaced.add(key)
        else:
            out_lines.append(line)
    for key, value in updates.items():
        if key not in replaced:
            out_lines.append(_format_env_line(key, value))

    tmp_path = ENV_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines) + '\n')
    os.replace(tmp_path, ENV_PATH)

    _apply_runtime()
    logger.info('LLM 配置已更新并热生效: base=%s model=%s', api_base, model)

    # 从刚落盘的文件回读作为响应：语义是"本次调用持久化了什么"，不依赖
    # 热更新是否被 mock/跳过，测试也无需拖起真实模型栈。
    persisted = dotenv_values(ENV_PATH)
    config = {
        'api_base': persisted.get('OPENAI_API_BASE') or '',
        'model': persisted.get('OPENAI_MODEL') or '',
        'api_key_masked': mask_key(persisted.get('OPENAI_API_KEY')),
    }
    from configs.llm_predictor import _CONTEXT_WINDOWS

    if model not in _CONTEXT_WINDOWS:
        config['warning'] = f'模型 {model} 不在上下文窗口表中，将按默认 32768 处理'
    return config


def _apply_runtime() -> None:
    """刷新 load_env 模块全局并重建 Settings.llm（热生效核心）。

    llama_index/torch 的 import 开销大，放在函数内：只有真正写入配置时
    才付出这部分成本，测试加载本模块也不会拖起整个模型栈。
    """
    import configs.load_env as load_env

    load_env.reload_env_variables()

    from configs.llm_predictor import build_llm
    from llama_index.core import Settings

    Settings.llm = build_llm()


def probe_endpoint(api_base: str, api_key: str | None = None) -> dict:
    """探测 OpenAI 兼容端点：GET {base}/models，返回可用模型列表与延迟。

    不抛异常——探测本来就是探"能不能通"，失败原因作为结构化结果返回给
    前端展示，比 500 干净。

    SSRF 缓解：只允许 http(s)（挡掉 file:// 这类万能协议）、不跟随重定向
    （防止 http 端点 302 跳内网地址）。刻意**不**封禁私网/localhost IP——
    这是管理员专用工具，探本机 ollama、内网网关是正当用法，鉴权
    （CUITCCA_API_KEY）才是这条边界的安全假设。
    """
    import configs.load_env as load_env

    base = (api_base or '').rstrip('/')
    if not base:
        return {'ok': False, 'error': 'Base URL 不能为空'}
    if not base.startswith(('http://', 'https://')):
        return {'ok': False, 'error': 'Base URL 必须以 http:// 或 https:// 开头'}

    key = api_key or load_env.openai_api_key or ''
    headers = {'Authorization': f'Bearer {key}'} if key else {}
    t0 = time.perf_counter()
    try:
        response = httpx.get(
            f'{base}/models',
            headers=headers,
            timeout=_PROBE_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        return {'ok': False, 'error': f'连接失败: {exc}'}
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if response.status_code != 200:
        return {
            'ok': False,
            'error': f'HTTP {response.status_code}: {response.text[:200]}',
            'latency_ms': latency_ms,
        }
    try:
        payload = response.json()
    except ValueError:
        return {'ok': False, 'error': '响应不是合法 JSON', 'latency_ms': latency_ms}

    models = sorted(
        item.get('id', '') for item in payload.get('data', []) if isinstance(item, dict)
    )
    return {'ok': True, 'models': models, 'latency_ms': latency_ms}
