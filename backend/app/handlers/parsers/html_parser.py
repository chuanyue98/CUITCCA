""".html/.htm：用 BeautifulSoup 提取正文，去掉脚本/样式/导航等噪音。

目前语料里没有 html 文件（Web 连接器还没落地），这个解析器是为后续
Web 爬虫连接器（``backend/app/connectors/``，另一个 agent 在做）抓回来的页面
准备的——先把解析能力铺好，注册表统一分派，等连接器接进来时直接能用。
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from ._source import Source, read_all_bytes
from .types import ParseResult

# 这些标签的内容不是正文：脚本/样式是代码，nav/header/footer/aside 通常是
# 站点通用导航栏/页脚，混进正文会稀释检索到的有效信息。
_NOISE_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript")


def parse_html(source: Source) -> ParseResult:
    raw = read_all_bytes(source)
    if not raw:
        return ParseResult.success("")
    try:
        soup = BeautifulSoup(raw, "lxml")
    except Exception as e:
        return ParseResult.failure(f"{type(e).__name__}: {e}")

    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.split("\n")]
    cleaned = "\n".join(line for line in lines if line)
    return ParseResult.success(cleaned)
