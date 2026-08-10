"""表格感知的分块器：不把 Markdown 表格拦腰切断。

## 要解决的问题（有实测数据，不是臆想）

解析器（``handlers/parsers/``）花了不少力气把 PDF/docx/pptx 里的表格还原成
Markdown 表格，保住"哪一行对应哪一列"的结构。但摄取管道后面接的是
``SentenceSplitter``，它只认句子边界和字符数，完全不知道 Markdown 表格是个
整体——实测在 ``信息搜集汇总/`` 全语料上：

    含 Markdown 表格的文档: 39 个，表格 508 张
    这些文档切出的 chunk: 294 个
    表格被腰斩的 chunk: 20 个（6.8%）

最差的 ``成都信息工程大学本科学生转专业申请表.docx`` 5 个 chunk 里断了 4 个。

"腰斩"的具体后果是：表格的续接部分被切进下一个 chunk，而**表头留在了上一个
chunk 里**。于是这个 chunk 变成一堆没有列名的裸数据行——

    | 本科生 | 10册 | 一个月 | 1次 | 一个月 |
    | 硕士生 | 15册 | 二个月 | 1次 | 二个月 |

单看这段，没人（也没有 LLM）知道 "10册" 是借书上限还是别的什么，"一个月"
到底是借期还是续借期。检索命中了也答不对，等于前面做的表格结构化白做了。

## 策略：表格是原子单位

1. 把文本切成"表格段"和"散文段"交替的序列。
2. 散文段交给父类 ``SentenceSplitter`` 正常切（句子边界、overlap 等行为完全
   不变）。
3. 表格段**整块保留**；只有当单张表自己就超过 ``chunk_size`` 时才按行切，
   且**每一片都重复表头**——这样即使一张大表不得不拆开，每一片仍然是自洽的、
   能看懂列含义的表格。
4. 最后把相邻的小片段贪心合并回 ``chunk_size`` 以内，避免一堆小表格把文档
   切成过多碎片（碎片太多会稀释检索信号）。

## 已知取舍

- **跨段落没有 overlap**：``chunk_overlap`` 只在父类处理散文段的内部生效，
  段与段之间（比如"散文 -> 表格"）不做重叠。表格重复一遍前文本来也没有意义，
  而为了制造 overlap 去切表格恰恰是这个类要避免的事。
- 只认 ``| --- |`` 这种带分隔线的 GFM 表格，也就是**本项目解析器自己产出的
  格式**（见 ``handlers/parsers/markdown_table.py``）。手写语料里那种纯靠空格
  对齐的"视觉表格"识别不了，会当成普通散文处理——不误判成表格比强行识别更
  安全。
"""
from __future__ import annotations

import re
from collections.abc import Callable

from llama_index.core.node_parser import SentenceSplitter

# GFM 表格的分隔线行：| --- | --- |（允许对齐冒号 :---: 和多余空格）
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")

SizeFn = Callable[[str], int]
"""度量一段文本"有多大"的函数。必须与 ``chunk_size`` 同单位（token）。"""


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _segment_text(text: str) -> list[tuple[bool, str]]:
    """把文本切成 ``[(是否表格, 内容)]`` 的交替序列。

    判定一段是表格的依据是"出现了分隔线行"，而不是"有竖线"——正文里偶尔出现
    的竖线（比如 ``A|B`` 这种写法）不该被误判成表格。识别到分隔线后，向上把
    紧邻的表头行、向下把连续的数据行都并进同一个表格段。
    """
    lines = text.split("\n")
    separator_indices = {i for i, line in enumerate(lines) if _TABLE_SEPARATOR_RE.match(line)}
    if not separator_indices:
        return [(False, text)] if text else []

    is_table_line = [False] * len(lines)
    for idx in separator_indices:
        is_table_line[idx] = True
        # 向上并入表头（分隔线上面紧邻的那些 | ... | 行）
        i = idx - 1
        while i >= 0 and _is_table_row(lines[i]):
            is_table_line[i] = True
            i -= 1
        # 向下并入数据行
        i = idx + 1
        while i < len(lines) and _is_table_row(lines[i]):
            is_table_line[i] = True
            i += 1

    segments: list[tuple[bool, str]] = []
    buffer: list[str] = []
    current_is_table = is_table_line[0]
    for line, line_is_table in zip(lines, is_table_line, strict=True):
        if line_is_table != current_is_table:
            chunk = "\n".join(buffer).strip("\n")
            if chunk.strip():
                segments.append((current_is_table, chunk))
            buffer = []
            current_is_table = line_is_table
        buffer.append(line)
    chunk = "\n".join(buffer).strip("\n")
    if chunk.strip():
        segments.append((current_is_table, chunk))
    return segments


def _split_table_preserving_header(table: str, max_size: int, size_of: SizeFn) -> list[str]:
    """单张表超过 ``max_size`` 时按行切，每一片都带上表头 + 分隔线。

    ``size_of`` 必须和 ``chunk_size`` 用**同一个计量单位**（token，见
    ``TableAwareSentenceSplitter._split_table_aware`` 的说明），不能想当然用
    ``len()`` 数字符。

    没有表头（比如解析出来的表格第一行就是数据）时退化成纯按行切——重复一个
    不存在的表头没有意义。
    """
    lines = [line for line in table.split("\n") if line.strip()]
    separator_at = next((i for i, line in enumerate(lines) if _TABLE_SEPARATOR_RE.match(line)), None)
    if separator_at is None:
        header_lines: list[str] = []
        body_lines = lines
    else:
        header_lines = lines[: separator_at + 1]
        body_lines = lines[separator_at + 1 :]

    header_size = size_of("\n".join(header_lines)) if header_lines else 0

    parts: list[str] = []
    current: list[str] = []
    current_size = header_size
    for row in body_lines:
        row_size = size_of(row)
        # 已经装了内容、再装这一行就超了 -> 收一片，新起一片并重新带上表头
        if current and current_size + row_size > max_size:
            parts.append("\n".join(header_lines + current))
            current = []
            current_size = header_size
        current.append(row)
        current_size += row_size
    if current:
        parts.append("\n".join(header_lines + current))
    return parts or [table]


def _pack(pieces: list[str], max_size: int, size_of: SizeFn) -> list[str]:
    """把相邻片段贪心合并到 ``max_size`` 以内，减少碎片。

    合并后的实际大小用 ``size_of`` 对**拼接结果**重新度量，而不是把两段各自
    的大小加起来——分词不是线性可加的（两段拼接处的字符可能合并成一个 token，
    也可能多出一个），逐段累加会系统性地偏离真实值。
    """
    packed: list[str] = []
    buffer = ""
    for piece in pieces:
        if not piece.strip():
            continue
        if not buffer:
            buffer = piece
            continue
        merged = f"{buffer}\n\n{piece}"
        if size_of(merged) <= max_size:
            buffer = merged
        else:
            packed.append(buffer)
            buffer = piece
    if buffer:
        packed.append(buffer)
    return packed


class TableAwareSentenceSplitter(SentenceSplitter):
    """``SentenceSplitter`` 的表格感知版本。

    继承而不是重新实现：句子边界识别、``chunk_size``/``chunk_overlap`` 语义、
    以及 ``NodeParser`` 那一整套建 node/挂 ``ref_doc_id`` 关系的机制全部复用，
    这里只接管"文本怎么切成片"这一步（覆盖 ``split_text``）。没有表格的文本
    走下来和父类行为完全一致，是安全的原地替换。
    """

    # 下面两处都是**先在方法帧里取到父类的绑定方法**，再传/闭包进去。这个写法
    # 是被两个约束夹出来的，别"顺手简化"：
    #
    # - 不能写成 ``SentenceSplitter.split_text(self, chunk)`` 这种非绑定调用：
    #   llama_index 用 instrumentation 装饰器包了这些方法，装饰器内部按签名
    #   绑定参数，非绑定调用会让它把 self 当成 text，运行时抛
    #   "TypeError: missing a required argument: 'text'"。
    # - 也不能把零参数的 ``super()`` 搬进闭包里再调：``super()`` 依赖当前函数
    #   帧里的 self，在闭包帧里会抛 "RuntimeError: super(): no arguments"。
    #   （而先 ``parent = super()`` 再 ``parent.split_text`` 运行时没问题，但
    #   mypy 追踪不了那个变量，会报 "super" has no attribute。）

    def split_text(self, text: str) -> list[str]:
        return self._split_table_aware(text, super().split_text)

    def split_text_metadata_aware(self, text: str, metadata_str: str) -> list[str]:
        # 父类用这个方法把 metadata 占用的 token 从可用 chunk_size 里扣掉。
        # 必须一并覆盖：``MetadataAwareTextSplitter._parse_nodes`` 走的是这条
        # 路径，只覆盖 split_text 的话生产摄取链路根本不会调到我们的实现。
        parent_split = super().split_text_metadata_aware

        def _prose(chunk: str) -> list[str]:
            return parent_split(chunk, metadata_str)

        return self._split_table_aware(text, _prose)

    def _split_table_aware(self, text: str, prose_splitter: Callable[[str], list[str]]) -> list[str]:
        segments = _segment_text(text)
        if not any(is_table for is_table, _ in segments):
            # 没表格：完全走父类，行为零变化
            return prose_splitter(text)

        # ``chunk_size`` 是父类的 **token** 预算（默认 1024），不是字符数。早期
        # 实现直接拿 ``len(content)`` 去比，在中文语料上偏得很离谱——中文一个
        # 字往往就是 1 个以上的 token，于是"看着没超 1024 字符"的 chunk 实际
        # 一千几百个 token，凡是含表格的文档每一块都会超出配置的上限。这里统一
        # 用父类自己的分词器度量，保证和 ``SentenceSplitter`` 同一把尺子。
        size_of = self._token_size
        budget = self.chunk_size

        pieces: list[str] = []
        for is_table, content in segments:
            if is_table:
                if size_of(content) <= budget:
                    pieces.append(content)
                else:
                    for part in _split_table_preserving_header(content, budget, size_of):
                        if size_of(part) <= budget:
                            pieces.append(part)
                        else:
                            # 按行切完仍然超预算，只可能是**单独一行**就超了。
                            # 实测语料里真有这种：
                            # 成都市城乡居民（大学生）医疗保险常见问题解答.docx
                            # 把整篇 FAQ 塞进了一个表格单元格，那一行 2789 token。
                            # 这种情况下"保住表格结构"已经没有意义了（整张表就
                            # 一行、一列，本来也没有行列关系可言），继续硬保只会
                            # 产出一个远超预算、检索精度被稀释的巨块。交给散文
                            # 切分器按句子切开更有用。
                            pieces.extend(prose_splitter(part))
            else:
                pieces.extend(prose_splitter(content))
        return _pack(pieces, budget, size_of)
