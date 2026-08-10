""".doc（旧版 Word 二进制 / OLE2 复合文档格式）：解析 piece table 还原正文。

## 为什么不是"读 WordDocument 流然后当纯文本/UTF-16 硬解"

.doc 的正文并不是简单地从某个固定偏移量开始连续存放——Word 编辑过程中会
反复插入/删除，正文实际由多个"分段"（piece）拼成，每段各自记录自己在
``WordDocument`` 流里的起始偏移和是单字节（CP1252 系列）还是双字节
（UTF-16LE）编码，这份"怎么拼"的信息存在另一个流（``0Table``/``1Table``，
用哪个由 FIB 里的一个标志位决定）里的 piece table（规范里叫 Clx/PlcPcd）。
不解析它、直接对 WordDocument 流做整体解码，遇到只有一个 piece 的极简单文档
可能凑巧能读对，但只要文档被编辑过、有多个 piece，就会读出错位/夹杂垃圾
字节的文本——这也是为什么"用尽力而为的启发式提取"里，这里选择的启发式是
"解析 FIB 的固定偏移字段找到 piece table"，而不是"整个流硬解码再从里面挑
可打印字符"这种更粗暴的做法：前者对这批语料（申请表模板为主）实测能完整
还原表单文字，后者容易丢字/串行。

## 已知限制（这就是为什么整体判定为"降级"）

- 只处理 FIB 版本 >= Word 97（``nFib >= 0x00C1``，2003 及更早的常见 .doc 都是
  这个范围）；更古老的 Word 6.0/95 格式没有 Clx 结构，会解析失败并给出明确
  失败原因，不会返回胡乱拼出来的文本。
- fcClx/lcbClx 用的是 Word 97-2003 格式里固定的字节偏移（0x1A2），不是按
  规范完整解析变长的 ``FibRgFcLcb`` 数组逐字段定位——对绝大多数正常保存的
  .doc 文件成立，但理论上存在"来自非常旧的第三方软件生成、字段布局不标准"
  的边缘文件会解析出偏差甚至异常，这类情况会被下面的 try/except 兜住转成
  ``FAILURE``，不会静默返回错误内容。
- 不处理批注、脚注/尾注、文本框、域代码（页码/日期等自动更新字段）；这些
  被规范建为独立的 piece 类别（ccpFtn/ccpAtn 等），当前实现只取主正文段
  （不做 ccp 分类，简单按"table stream 里 Clx 记录的所有 piece"全部拼接，
  绝大多数简单表单类文档主文本就是唯一的 piece 类别，够用）。
- 控制字符（单元格分隔符 ``\\x07``、分节/分页符等）转换成空格/换行是启发式
  按经验替换，不保证和 Word 里的视觉排版完全一致。

因为存在以上简化，成功解析的结果一律标记 ``degraded=True``，metadata 里会
带上这条说明（见 ``ingestion_pipeline.documents_from_file``），不假装这份
文本和 docx/pdf 解析出来的一样可信。
"""
from __future__ import annotations

import re
import struct

import olefile

from ._source import Source, as_path_or_stream
from .types import ParseResult

_MIN_NFIB = 0x00C1  # Word 97 及以后；更早的格式没有 Clx，不支持
_FC_CLX_OFFSET = 0x1A2  # FibRgFcLcb97 里 fcClx/lcbClx 字段的固定偏移（见模块 docstring）

# 控制字符 -> 可读替换。\x07 是 Word 里的单元格/列表项分隔符，\r 是段落结束，
# \x0b 是段内软换行（Shift+Enter），其余（\x01/\x03/\x04/\x08 等）是各种
# 批注/域/图片占位符，直接丢弃。
_CONTROL_CHAR_MAP = {
    "\x07": " | ",
    "\r": "\n",
    "\x0b": "\n",
}
# 注意排除 \x0a（LF）：上面已经把 \r 换成了 \n（LF），这里如果连 \x0a 一起丢
# 就等于把自己刚生成的换行又吃掉了——这是实现时踩到的一个真实 bug，故此注释。
_DROP_CHARS_RE = re.compile(r"[\x00-\x09\x0b-\x0c\x0e-\x1f]")


def _clean_text(raw: str) -> str:
    for ch, repl in _CONTROL_CHAR_MAP.items():
        raw = raw.replace(ch, repl)
    raw = _DROP_CHARS_RE.sub("", raw)
    # 折叠连续空白/空行，Word 表单里大量用空格占位画"下划线"，原样保留没有
    # 信息量还会污染分块。
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.split("\n")]
    return "\n".join(line for line in lines if line)


def _extract_pieces(word_doc: bytes, table_stream: bytes) -> str:
    fc_clx, lcb_clx = struct.unpack("<II", word_doc[_FC_CLX_OFFSET : _FC_CLX_OFFSET + 8])
    clx = table_stream[fc_clx : fc_clx + lcb_clx]

    # Clx = 若干个 0x01 前缀的 RgPrc 块（格式属性，跳过）+ 一个 0x02 前缀的
    # Pcdt 块（piece table 本体，我们要的东西）。
    pcdt = None
    i = 0
    while i < len(clx):
        marker = clx[i]
        if marker == 1:
            i += 1
            cb = struct.unpack("<H", clx[i : i + 2])[0]
            i += 2 + cb
        elif marker == 2:
            i += 1
            lcb = struct.unpack("<I", clx[i : i + 4])[0]
            i += 4
            pcdt = clx[i : i + lcb]
            break
        else:
            raise ValueError(f"无法识别的 Clx 分段标记: {marker!r}")
    if pcdt is None:
        raise ValueError("Clx 里没有找到 Pcdt（piece table）分段")

    # PlcPcd: (n+1) 个 4 字节 CP（字符位置）+ n 个 8 字节 Pcd。
    n = (len(pcdt) - 4) // 12
    if n <= 0:
        raise ValueError("piece table 里没有任何分段")
    cps = struct.unpack(f"<{n + 1}i", pcdt[: 4 * (n + 1)])
    pcd_start = 4 * (n + 1)

    parts = []
    for k in range(n):
        pcd = pcdt[pcd_start + k * 8 : pcd_start + (k + 1) * 8]
        fc_raw = struct.unpack("<I", pcd[2:6])[0]
        is_ansi = bool((fc_raw >> 30) & 1)  # fCompressed：1 = 单字节 CP1252，0 = UTF-16LE
        fc = fc_raw & 0x3FFFFFFF
        if is_ansi:
            # MS-DOC 的 FcCompressed（2.9.73）：fCompressed=1 时字段里存的**不是**
            # 字节偏移本身，真实偏移是 fc/2；只有 fCompressed=0（UTF-16）才直接
            # 用 fc。少了这一步，压缩分段会从大约两倍远的位置开始读，解出来是
            # 乱码——而且因为整份文档只有部分分段是压缩的，表现为"正文读到一半
            # 突然变成乱码"，很容易被当成编码问题而不是偏移问题。
            #
            # 实测语料里 39 个 piece 中有 2 个是压缩分段
            # （附件4—本科生在读证明（普通本科英文版）.doc，英文正文用单字节
            # 存储正是 Word 的常规行为），修复前那份文档解出来是
            # "at Cheng" 后面接一串 ÄÈÊÎÐÔÖÚÜÞà…，正文被截断且混入垃圾字符。
            fc >>= 1
        n_chars = cps[k + 1] - cps[k]
        if n_chars <= 0:
            continue
        if is_ansi:
            raw_bytes = word_doc[fc : fc + n_chars]
            parts.append(raw_bytes.decode("cp1252", errors="replace"))
        else:
            raw_bytes = word_doc[fc : fc + n_chars * 2]
            parts.append(raw_bytes.decode("utf-16-le", errors="replace"))
    return "".join(parts)


def parse_doc(source: Source) -> ParseResult:
    try:
        ole = olefile.OleFileIO(as_path_or_stream(source))
    except Exception as e:
        return ParseResult.failure(f"不是有效的 OLE2 复合文档: {type(e).__name__}: {e}")

    try:
        if not ole.exists("WordDocument"):
            return ParseResult.failure("OLE2 容器里没有 WordDocument 流，不是 .doc 文件")
        word_doc = ole.openstream("WordDocument").read()

        nfib = struct.unpack("<H", word_doc[2:4])[0]
        if nfib < _MIN_NFIB:
            return ParseResult.failure(
                f"检测到 Word 6.0/95 格式（nFib=0x{nfib:04x}），不支持——" "该格式没有 piece table，需要不同的解析方式"
            )

        flags = struct.unpack("<H", word_doc[0xA:0xC])[0]
        f_which_tbl_stm = (flags >> 9) & 1
        table_stream_name = "1Table" if f_which_tbl_stm else "0Table"
        if not ole.exists(table_stream_name):
            return ParseResult.failure(f"缺少 {table_stream_name} 流，无法定位 piece table")
        table_stream = ole.openstream(table_stream_name).read()

        raw_text = _extract_pieces(word_doc, table_stream)
    except Exception as e:
        return ParseResult.failure(f"piece table 解析失败: {type(e).__name__}: {e}")
    finally:
        ole.close()

    text = _clean_text(raw_text)
    if not text:
        return ParseResult.success("", degraded=True, reason="piece table 解析成功但没有提取到可读正文")
    return ParseResult.success(
        text,
        degraded=True,
        reason="启发式 piece table 解析（简化实现，不处理批注/脚注/域代码，见 doc_parser.py 模块说明）",
    )
