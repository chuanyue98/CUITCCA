"""YAML front-matter 的解析：把 Markdown 文件头部的 ``---`` 块拆成 metadata。

## 为什么这属于"解析"而不是"连接器"

Web 连接器（``backend/app/connectors/``）抓回来的每篇文档都写成"YAML
front-matter + Markdown 正文"，front-matter 里是溯源信息（``source_url``、
``publish_date``、``category``…）。这些字段是知识库的核心资产——检索时要用
它们做过滤、回答时要用它们做引用溯源。

但摄取管道按扩展名分派解析器，``.md`` 走的是 ``text_parser``，它只做编码
解码、原样返回全文。结果是：front-matter 会**混进正文**变成 chunk 里的噪音
（"source_url: https://..." 被当成正文送去 embedding），而真正该进 metadata
的字段一个都没进去。

所以 front-matter 处理必须发生在"文本 -> Document"这一层，且它是 Markdown
这种**文档格式**本身的约定，不是某个数据源特有的——放在 parsers 包里，让
连接器和摄取管道共用同一个实现，而不是两边各写一遍（``connectors/
markdown_io.py`` 的 ``parse_front_matter`` 现在就是从这里导入的）。
"""
from __future__ import annotations

from typing import Any

import yaml

_DELIMITER = "---"


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """拆出 ``(front_matter_dict, body)``。

    没有 front-matter、或者 YAML 解析失败、或者解析出来不是一个 dict 时，
    一律返回 ``({}, 原文)``——**绝不能因为头部格式不对就丢掉正文**。语料文件
    可能来自各种手工编辑，一个坏掉的 YAML 头不应该让整篇内容进不了知识库；
    退化成"当作没有 metadata 的普通 Markdown"是安全的降级。
    """
    if not text.startswith(_DELIMITER):
        return {}, text

    # 找结束分隔符：必须是行首的 ---，不能用裸 find("---")，否则正文里出现的
    # 分隔线（Markdown 的水平线也写作 ---）会把 front-matter 提前截断。
    end = text.find(f"\n{_DELIMITER}", len(_DELIMITER))
    if end == -1:
        return {}, text

    fm_text = text[len(_DELIMITER) : end]
    body = text[end + len(_DELIMITER) + 1 :].lstrip("\n")

    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return data, body


# 允许提升进 Document metadata 的 front-matter 字段白名单。
#
# 用白名单而不是"有什么塞什么"，有两个实际原因：
# 1. metadata 会参与 ``TextNode.hash`` 的计算（见本包外层
#    ingestion_pipeline 模块 docstring 里关于 last_updated 的说明），塞进去
#    的字段越多、越容易变动，增量去重就越容易失效。
# 2. metadata 默认会跟着 chunk 一起进 embedding 和 LLM 上下文，塞无关字段
#    等于污染检索文本、浪费 token。
PROMOTED_KEYS = ("source_url", "title", "publish_date", "category", "site")


def promoted_metadata(front_matter: dict[str, Any]) -> dict[str, str]:
    """按白名单挑出要写进 Document metadata 的字段，统一成字符串。

    值为 ``None``/空的字段直接不写——比如静态页面解析不到发布日期时
    ``publish_date`` 是 ``None``，写成字符串 ``"None"`` 反而会让下游以为
    "有这么个日期"。缺字段和字段为空是两回事，这里保持前者。
    """
    out: dict[str, str] = {}
    for key in PROMOTED_KEYS:
        value = front_matter.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out[key] = text
    return out
