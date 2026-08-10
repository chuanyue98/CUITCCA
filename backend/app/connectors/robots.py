"""robots.txt 合规检查：抓取前先问一遍"这个 URL 允许抓吗"。

用标准库 ``urllib.robotparser`` 做规则匹配（不用自己重新实现 robots.txt 语
法），但不用它内置的 ``read()``（那个方法自己发 urllib 请求，绕过了我们注入
的 httpx client，测试里也没法 mock）——改成自己用 httpx 拉 robots.txt 文本，
再喂给 ``RobotFileParser.parse()``，这样整个连接器只有一条"发请求"的路径，
好测、好加限速。
"""
from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


class RobotsChecker:
    """按 base_url 缓存已解析的 robots.txt 规则，避免每个 URL 都重新拉一次
    robots.txt。"""

    def __init__(self, client: httpx.Client, user_agent: str, timeout_seconds: float = 10.0):
        self._client = client
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._parsers: dict[str, RobotFileParser] = {}

    def _base_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _get_parser(self, base_url: str) -> RobotFileParser:
        if base_url in self._parsers:
            return self._parsers[base_url]

        parser = RobotFileParser()
        robots_url = f"{base_url}/robots.txt"
        try:
            resp = self._client.get(robots_url, timeout=self._timeout)
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
            else:
                # 没有 robots.txt（404 等）按标准约定视为"未声明限制"，允许抓取
                # ——CUIT 官网实测就是这种情况（/robots.txt 返回站内 404 跳转页）。
                parser.parse([])
        except httpx.HTTPError:
            # 拉取 robots.txt 本身失败（超时/连接错误）时保守处理：视为"未声明
            # 限制"而不是"整站禁止"，因为后者会让一次网络抖动误伤整个站点的
            # 抓取；真正的访问失败会在抓正文时的重试逻辑里体现和记录。
            parser.parse([])
        self._parsers[base_url] = parser
        return parser

    def is_allowed(self, url: str) -> bool:
        parser = self._get_parser(self._base_url(url))
        return parser.can_fetch(self._user_agent, url)
