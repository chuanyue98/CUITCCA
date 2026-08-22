"""graph 路由的会话状态：按 client_id（= 会话 cookie 的 session_id）隔离的
聊天历史与最近一次来源节点。

独立成模块的原因：graph.py 拆成 qa/agent/ask/feedback 四个子路由后，这些
状态是四组端点唯一的共享物（写历史的和读历史的在不同端点），必须放在大家
都能 import 的地方而不是任何一方的模块里。TTLCache 的容量/过期参数原来写
死在 graph.py 顶部，原样搬过来。
"""
import time
from collections import OrderedDict

from fastapi import Request

# 会话缓存最大容量
_MAX_SESSIONS = 200
_SESSION_TTL = 3600  # 1小时


class TTLCache:
    """简单的 TTL + LRU 缓存，替代裸 dict"""

    def __init__(self, max_size: int = _MAX_SESSIONS, ttl: int = _SESSION_TTL):
        self._data: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key):
        entry = self._data.get(key)
        if entry is None:
            return None
        if time.time() - entry[1] > self._ttl:
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return entry[0]

    def set(self, key, value):
        self._data[key] = (value, time.time())
        self._data.move_to_end(key)
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)

    def __contains__(self, key):
        return self.get(key) is not None

    def __len__(self):
        return len(self._data)


def _client_id(request: Request) -> str:
    if hasattr(request.state, "session_id"):
        return request.state.session_id
    return request.cookies.get("session_id") or "unknown"


_chat_histories: TTLCache = TTLCache()
_last_query_response: TTLCache = TTLCache()
