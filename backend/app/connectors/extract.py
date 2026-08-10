"""HTML 正文抽取：从整页 HTML 里挖出标题/日期/正文，去掉导航/脚本等噪音，
表格转成 Markdown 表格保留行列关系。

纯函数模块——输入是 HTML 字符串，输出是字符串/dataclass，不发请求、不摸
文件系统，方便用固定的 HTML fixture 做单测，覆盖率和执行速度都比"下真实
网页跑测试"好得多。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

# 抓下来的详情页里，这些标签整体没有正文价值（导航/脚本/样式/表单控件），
# 在挑出正文容器之后统一先删掉，避免污染 Markdown 输出。
_NOISE_TAGS = ("script", "style", "noscript", "iframe", "nav", "footer", "header", "form", "button")

# 发布日期最常见的两种中文表达形式；两种都尝试，命中第一个即可。
_DATE_PATTERNS = (
    re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})"),
)


@dataclass
class ListingItem:
    """列表页里的一条条目：详情页链接 + 列表页上就能看到的标题/日期。"""

    url: str
    title: str
    publish_date: str | None


def _select_first(soup: BeautifulSoup | Tag, selector_csv: str) -> Tag | None:
    """``selector_csv`` 是逗号分隔的多个候选 CSS 选择器（配置里写成一行，
    比如 "div.v_news_content, div#vsb_content"）。逐个尝试，返回第一个能选到
    "有实际文本内容"元素的选择器结果——只是"选择器匹配到标签"不够，标签可能
    是空壳（比如某些页面正文容器有但没塞内容），那种情况要继续试下一个候选。
    """
    for raw in selector_csv.split(","):
        selector = raw.strip()
        if not selector:
            continue
        found = soup.select_one(selector)
        if found is not None and found.get_text(strip=True):
            return found
    return None


def _normalize_date(text: str) -> str | None:
    for pattern in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            year, month, day = m.groups()
            try:
                return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            except ValueError:
                continue
    return None


def extract_title(soup: BeautifulSoup, title_selector_csv: str, fallback: str = "") -> str:
    """标题优先取正文区域内的标题标签（比如 ``h2.tit``），比 ``<title>``
    整页标题更准——后者往往带 "-成都信息工程大学" 这类站点后缀。"""
    found = _select_first(soup, title_selector_csv)
    if found is not None:
        text = found.get_text(strip=True)
        if text:
            return text
    # 常见候选都没命中时退化到 <title>，并去掉站点名后缀（用" - "/"-"切分取
    # 第一段），聊胜于无。
    title_tag = soup.find("title")
    if title_tag is not None:
        text = title_tag.get_text(strip=True)
        if text:
            return re.split(r"[-—]", text)[0].strip() or text
    return fallback


def extract_publish_date(soup: BeautifulSoup, date_selector_csv: str) -> str | None:
    """先在指定的日期区域（比如 ``p.conttime``，形如"日期：2026-08-05"）里找，
    找不到再退化到全文兜底搜索——静态介绍页往往没有 conttime 这种结构化日期
    区块，此时宁可返回 None 也不去正文里瞎猜，除非全文能明确搜到一个日期
    模式。"""
    found = _select_first(soup, date_selector_csv)
    if found is not None:
        date = _normalize_date(found.get_text(" ", strip=True))
        if date:
            return date
    return None


def clean_content_node(node: Tag) -> None:
    """就地删除正文容器内的噪音标签（脚本/样式/导航等）。"""
    for tag in node.find_all(_NOISE_TAGS):
        tag.decompose()


def table_to_markdown(table: Tag) -> str:
    """把 ``<table>`` 转成 Markdown 表格，保留行列关系——这是任务要求里
    特别强调的一点，很多规章制度类页面（比如课程设置、招生计划）核心信息就
    在表格里，直接拍平成纯文本会丢掉"哪个数字对应哪一列"这种结构信息。"""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        rows.append([c.get_text(" ", strip=True).replace("\n", " ") for c in cells])
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
# 只挑这几类"叶子级"块标签做段落抽取，刻意不包含 div/section 之类的通用
# 容器标签——CMS 页面里 div 经常层层嵌套包裹 p，如果 div 和它内部的 p 都被
# 当作独立块处理，同一段文字会被输出两次。真实抓到的页面（见
# ``connectors/sites.yaml`` 注释里记录的实测结构）正文统一用 <p> 包段落，
# 这个选择覆盖了实际场景；极少数没有 p 标签、直接把文本堆在 div 里的页面，
# 靠 ``html_to_markdown`` 的"一个块都没抽到就整体取纯文本"兜底。
_LEAF_BLOCK_TAGS = ("p", "li")
_TABLE_PLACEHOLDER_RE = re.compile(r"\x00TABLE_(\d+)\x00")


def _placeholder_tag(text: str) -> Tag:
    """构造一个只包含占位文本的 ``<p>`` 标签，用来在原位替换掉表格——这样
    "表格在正文中的第几段"这个顺序信息不会丢，后续按文档顺序遍历时能在
    原来的位置插回转换好的 Markdown 表格。"""
    tag = BeautifulSoup("<p></p>", "lxml").p
    assert tag is not None
    tag.string = text
    return tag


def _render_node(node: Tag) -> list[str]:
    """把正文容器内的元素树渲染成 Markdown 片段列表：表格转 Markdown 表格
    （原位替换，保留在正文中的顺序），标题保留 # 前缀，列表项加 "- " 前缀，
    其余按 ``<p>`` 段落处理。"""
    table_markdowns: list[str] = []
    for idx, table in enumerate(node.find_all("table")):
        md = table_to_markdown(table)
        table_markdowns.append(md)
        table.replace_with(_placeholder_tag(f"\x00TABLE_{idx}\x00"))

    out: list[str] = []
    for el in node.find_all(list(_HEADING_TAGS) + list(_LEAF_BLOCK_TAGS)):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        placeholder_match = _TABLE_PLACEHOLDER_RE.fullmatch(text)
        if placeholder_match:
            idx = int(placeholder_match.group(1))
            if table_markdowns[idx]:
                out.append(table_markdowns[idx])
            continue
        if el.name in _HEADING_TAGS:
            level = int(el.name[1])
            out.append(f"{'#' * level} {text}")
        elif el.name == "li":
            out.append(f"- {text}")
        else:
            out.append(text)
    return out


def html_to_markdown(node: Tag) -> str:
    """正文容器 -> Markdown 正文字符串。表格转 Markdown 表格，标题/列表保留
    结构标记，其余段落按纯文本输出（去广告/样式后的正文本身信息密度已经
    足够，没必要保留原始 HTML 的字体/颜色等样式信息）。"""
    clean_content_node(node)
    blocks = _render_node(node)
    if not blocks:
        # 没有命中任何块级标签时，退化为整体取纯文本，避免"选中了正文容器
        # 但内部是没有 p/div 包裹的纯文本节点"这种边界情况丢内容。
        text = node.get_text("\n", strip=True)
        return text
    # 去重相邻重复空行，合并成规整的 Markdown。
    return "\n\n".join(blocks)


@dataclass
class ExtractedPage:
    title: str
    publish_date: str | None
    content_markdown: str


# 兜底路径专用：精确正文选择器都没命中时，剥掉整页里明显是界面外壳（导航/
# 页脚/搜索框/面包屑等）的元素，剩下的 <body> 内容整体当正文用。命中范围
# 刻意宽松（宁可多剥一点导航碎片，也不要把真正的正文当噪音删掉）。
_CHROME_NOISE_CLASS_RE = re.compile(
    r"nav|menu|footer|header|search|logo|banner|breadcrumb|sidebar|share|social|backtop|toolbar", re.I
)
_CHROME_NOISE_TAGS = ("script", "style", "noscript", "header", "footer", "nav", "form", "iframe", "button")


def _strip_chrome_noise(soup: BeautifulSoup) -> None:
    for tag in soup(_CHROME_NOISE_TAGS):
        tag.decompose()
    # find_all 先取快照再遍历删除：上面按标签名整体删除后，快照里某些元素
    # 可能已经随父节点一起被 decompose，此时 el.attrs 会变成 None，用它做
    # 判断跳过即可，不需要特殊处理异常。
    for el in soup.find_all(True):
        if el.attrs is None:
            continue
        raw_classes: Any = el.get("class") or []
        classes: list[str] = raw_classes if isinstance(raw_classes, list) else [str(raw_classes)]
        el_id = str(el.get("id") or "")
        if any(_CHROME_NOISE_CLASS_RE.search(c) for c in classes) or _CHROME_NOISE_CLASS_RE.search(el_id):
            el.decompose()


def _body_fallback_node(html: str) -> Tag | None:
    """精确正文选择器一个都没命中时的兜底：整页去掉导航/页脚等界面元素后，
    把 ``<body>`` 剩下的部分整体当正文。用于站点里少数不走标准文章模板、
    自定义排版的"专题型"静态页面（比如学校概况类页面实测就是这种情况——
    没有统一的 ``v_news_content`` 容器）。代价是可能残留少量侧边栏/面包屑
    文字，属于已知的精度取舍，见 ``docs/data-sources.md`` 的已知限制说明。

    独立重新解析一遍 HTML，不复用调用方已有的 soup——避免为了给兜底路径
    剥导航，误伤本该保留给标题/日期抽取用的原始 soup（后者的选择器可能
    依赖 header/footer 内部的元素，虽然目前没有这种配置，但没必要让两条
    路径共享可变状态）。
    """
    fallback_soup = BeautifulSoup(html, "lxml")
    _strip_chrome_noise(fallback_soup)
    body = fallback_soup.body or fallback_soup
    if isinstance(body, Tag) and body.get_text(strip=True):
        return body
    return None


def extract_page(
    html: str,
    *,
    content_selector_csv: str,
    title_selector_csv: str,
    date_selector_csv: str,
    fallback_title: str = "",
    allow_body_fallback: bool = True,
) -> ExtractedPage | None:
    """整页抽取入口：解析 HTML，挑正文容器，产出标题/日期/Markdown 正文。

    配置的正文选择器都没命中时，默认（``allow_body_fallback=True``）会退化
    到 ``_body_fallback_node`` 的"去噪后取整个 body"策略，而不是直接判定
    失败——宁可产出一篇精度稍打折扣的文档，也不要因为个别页面模板和主流程
    不一致就整篇丢弃。两条路径都拿不到非空正文时才返回 ``None``，这种情况
    多半是页面本身有问题（抓到错误页/改版页），调用方应该当失败处理。
    """
    soup = BeautifulSoup(html, "lxml")
    content_node = _select_first(soup, content_selector_csv)
    used_fallback = False
    if content_node is None and allow_body_fallback:
        content_node = _body_fallback_node(html)
        used_fallback = True
    if content_node is None:
        return None
    title = extract_title(soup, title_selector_csv, fallback=fallback_title)
    publish_date = extract_publish_date(soup, date_selector_csv)
    content_markdown = html_to_markdown(content_node)
    if not content_markdown.strip():
        return None
    if used_fallback:
        # 兜底路径的正文里可能混了少量没被去噪规则命中的导航碎片，起始处
        # 加一行说明，不掩盖这是精度打了折扣的产出，方便下游/人工核查时
        # 一眼识别。
        content_markdown = "<!-- 注：本页正文经通用兜底规则提取，可能包含少量非正文碎片 -->\n\n" + content_markdown
    return ExtractedPage(title=title, publish_date=publish_date, content_markdown=content_markdown)


# 列表页翻页控件里"当前页/总页数"的标记，比如 "1/193"。CUIT 站群 CMS
# （网站群通用模板）的分页组件固定用 <span class="p_t">当前/总数</span>
# 渲染，同时在页面内嵌的翻页 JS 调用里也会把总页数当第一个参数传入，两处
# 互为冗余校验，任意一处命中即可。
_TOTAL_PAGES_PATTERNS = (
    re.compile(r'class="p_t">\s*\d+\s*/\s*(\d+)\s*<'),
    re.compile(r"_simple_list_gotopage_fun\((\d+)"),
)


def discover_total_pages(html: str) -> int | None:
    """从列表首页的翻页控件里解析总页数。解析不到时返回 None，调用方应
    回退到配置里显式写的 ``total_pages`` 或干脆只抓第 1 页。"""
    for pattern in _TOTAL_PAGES_PATTERNS:
        m = pattern.search(html)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def extract_listing_items(html: str, base_url: str, item_selector: str) -> list[ListingItem]:
    """从列表页解析出条目：详情页 URL（已解析成绝对地址）、标题、发布日期。

    CUIT 站群 CMS 的列表项固定形如
    ``<li><a href="../info/x/y.htm" title="标题">...<span>2026-08-05</span></a></li>``
    ——标题优先取 ``title`` 属性（比标签内文本更不容易被内部 ``<h3>`` 的换行/
    多余空白干扰），日期取链接内第一个匹配日期格式的 ``<span>`` 文本。
    """
    soup = BeautifulSoup(html, "lxml")
    items: list[ListingItem] = []
    seen: set[str] = set()
    for a in soup.select(item_selector):
        href = a.get("href")
        if not href or not isinstance(href, str):
            continue
        url = urljoin(base_url + "/", href)
        if url in seen:
            continue
        title = a.get("title")
        if not isinstance(title, str) or not title.strip():
            title = a.get_text(" ", strip=True)
        title = title.strip()
        if not title:
            continue
        publish_date = None
        for span in a.find_all("span"):
            date = _normalize_date(span.get_text(strip=True))
            if date:
                publish_date = date
                break
        seen.add(url)
        items.append(ListingItem(url=url, title=title, publish_date=publish_date))
    return items
