""".jpg/.jpeg/.png：OCR 识别图片里的文字（流程图、表单截图等）。

OCR 引擎 ``rapidocr-onnxruntime`` 是可选依赖（见 ``pyproject.toml``
``[project.optional-dependencies].ocr``），语料里只有 4 个图片文件需要它
（"休学流程.jpg""复学流程.jpg" 这类流程图截图），为这一个能力强制所有部署
都装一个约 100MB 的 onnxruntime 模型不划算。

## 未安装时的行为：显式"能力不可用"，不是静默跳过、不是崩溃

这是本次改造要解决的核心问题之一——原来 ``ALLOWED_EXTENSIONS`` 里没有图片
格式，图片直接在上传校验那一步就被拒绝，"看不见"；现在图片能被摄取管道
接收，但如果这台机器没装 OCR 依赖，必须让调用方明确知道"这个文件本来能处理
但依赖没装"，而不是既不报错也不产出内容。识别方式：``import`` 失败时
返回 ``ParseResult.unavailable``，reason 里带上安装命令
``uv sync --extra ocr``；真正装了依赖之后，OCR 引擎本身识别失败（图片损坏、
没有文字内容）才归类为 ``FAILURE``。
"""
from __future__ import annotations

import importlib.util

from ._source import Source, as_path_or_stream
from .types import ParseResult

_INSTALL_HINT = "OCR 依赖（rapidocr-onnxruntime）未安装，运行 `uv sync --extra ocr` 后重试"


def _ocr_available() -> bool:
    return importlib.util.find_spec("rapidocr_onnxruntime") is not None


def parse_image(source: Source) -> ParseResult:
    if not _ocr_available():
        return ParseResult.unavailable(_INSTALL_HINT)

    try:
        import numpy as np
        from PIL import Image
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        # 理论上 _ocr_available() 已经挡住了这种情况，这里是双重保险
        # （比如 rapidocr 装了但它自己的依赖如 onnxruntime 缺失/版本不兼容）。
        return ParseResult.unavailable(f"{_INSTALL_HINT}（导入时出错: {e}）")

    try:
        image = Image.open(as_path_or_stream(source)).convert("RGB")
        engine = RapidOCR()
        result, _elapsed = engine(np.array(image))
    except Exception as e:
        return ParseResult.failure(f"OCR 识别失败: {type(e).__name__}: {e}")

    if not result:
        return ParseResult.success("", degraded=True, reason="OCR 未识别出任何文字（图片可能是纯图形/无文字内容）")

    # rapidocr 返回 [(box, text, score), ...]，按识别顺序（大致是从上到下）
    # 拼接即可；流程图这类图片本来就没有强阅读顺序，不追求精确排版还原。
    lines = [text for _box, text, _score in result if text.strip()]
    return ParseResult.success(
        "\n".join(lines),
        degraded=True,
        reason="OCR 识别结果，可能有误识别；未做版面分析，多列/多分支流程图的阅读顺序不保证正确",
    )
