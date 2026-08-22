"""语料落盘：把 ``CrawledDocument`` 写成带 YAML front-matter 的 Markdown
文件，文件名由 URL 稳定派生。

## 文件名为什么只由 URL 决定，不掺标题

增量抓取要求"同一 URL 每次抓取产出同一文件名，便于增量覆盖"——如果文件名里
掺了标题，标题被网站编辑改一个字（错别字修正、加个"【已结束】"前缀之类），
同一个 URL 下次就会算出不同文件名，产生一个新文件而不是覆盖旧文件，旧文件
变成孤儿、永远不会被清理，语料库里同一页面出现两份内容不同的版本，是比较
隐蔽的数据质量问题。标题只出现在 front-matter 和正文标题里，不参与文件名。

## 中文字符处理

URL 本身通常是 ASCII，但为了不对"某个二级站点用中文路径/查询串"这种未来
情况假设太多，文件名生成统一走 ``sanitize_filename_component``——把非法
文件名字符（路径分隔符、空白、Windows 也不允许的 ``:*?"<>|``）替换成下划线，
中文字符本身在类 Unix 文件系统上合法，原样保留即可，只做 NFKC 归一化避免
全角/半角变体造成的视觉重复但字节不同的文件名。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from connectors.base import CrawledDocument
from handlers.parsers.front_matter import split_front_matter

_ILLEGAL_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|\s]+')
_TRIM_CHARS = "._"


def sanitize_filename_component(text: str, max_length: int = 120) -> str:
    """把任意文本（可能含中文、URL 特殊字符）转成一个安全的文件名片段。"""
    normalized = unicodedata.normalize("NFKC", text)
    cleaned = _ILLEGAL_FILENAME_CHARS_RE.sub("_", normalized).strip(_TRIM_CHARS)
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_length]


def stable_filename(url: str) -> str:
    """由 URL 确定性派生 .md 文件名：域名+路径清洗后做人类可读的主体，
    再拼一段 URL 的短 sha1 摘要防止清洗后撞名（两个不同 URL 清洗掉的恰好
    只是被替换成下划线的那部分字符）。查询串/锚点不参与派生——这套 CMS
    的页面寻址不依赖它们，见模块级说明。"""
    parsed = urlparse(url)
    readable = sanitize_filename_component(f"{parsed.netloc}{parsed.path}")
    digest = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"{readable}__{digest}.md"


def render_markdown(doc: CrawledDocument) -> str:
    """渲染成 "YAML front-matter + 正文" 的 Markdown 文本。字段顺序固定
    （``sort_keys=False``），方便人工 diff 增量更新时一眼看出变了什么。"""
    front_matter = {
        "source_url": doc.source_url,
        "title": doc.title,
        "publish_date": doc.publish_date,
        "category": doc.category,
        "site": doc.site,
        "crawled_at": doc.crawled_at,
        "content_hash": doc.content_hash,
    }
    fm_yaml = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False, default_flow_style=False)
    body = doc.content_markdown.strip()
    return f"---\n{fm_yaml}---\n\n# {doc.title}\n\n{body}\n"


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """``render_markdown`` 的逆操作：从文件内容里解析出 front-matter dict 和
    正文。

    实现在 ``handlers/parsers/front_matter.py``——摄取管道同样需要拆
    front-matter（把溯源字段提升成 Document metadata，而不是让那段 YAML 混进
    正文被 embedding），两边共用一个实现，避免"连接器写的格式"和"摄取端读的
    格式"各自演化后对不上。这里保留同名函数只是为了让连接器这一侧的调用方
    （测试、采集结果核对）不必知道它实际住在哪个包里。
    """
    return split_front_matter(text)


def write_markdown_file(doc: CrawledDocument, out_dir: Path) -> Path:
    """把文档写到 ``out_dir/stable_filename(source_url)``，返回实际写入的
    路径。同一 URL 反复调用会覆盖同一个文件（这正是"增量覆盖"要的行为）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / stable_filename(doc.source_url)
    path.write_text(render_markdown(doc), encoding="utf-8")
    return path
