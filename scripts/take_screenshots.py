"""用 Playwright 自动截取 CUITCCA 四个前端页面的 Demo 截图。

用途
    维护者本地运行一次，生成 README 引用的截图（docs/screenshots/*.png）。
    截图不存在时 README 显示 broken image 是正常的，跑完本脚本后即有图。

前置条件
    1. 后端已运行在 --base-url（默认 http://localhost:8522）：
         make dev            # 或: cd backend && uv run python app/main.py
    2. 已安装 Playwright 与 Chromium：
         pip install playwright
         playwright install chromium
    3.（聊天页要截"已发送消息"状态）后端需配置好可用 LLM：
         编辑 backend/.env 填入 OPENAI_API_KEY；CUITCCA_API_KEY 留空便于本地免鉴权。

用法
    uv run python scripts/take_screenshots.py
    uv run python scripts/take_screenshots.py --base-url http://localhost:8522 --output-dir docs/screenshots

输出
    docs/screenshots/chat.png          聊天页（已发送一条消息并收到回复）
    docs/screenshots/manage.png        知识库管理页（已加载索引列表）
    docs/screenshots/feed_back.png     反馈页
    docs/screenshots/use_function.png  使用指南页

说明
    - 聊天页会模拟输入一条问题、点发送、等待回复到达后再截图；若 LLM 未配置
      或后端不可用，会退化为截"仅含用户消息"的状态并打印警告，不中断其余页面。
    - 管理页等待 #index-select 加载出真实索引选项后再截图；若无索引则截当前态。
    - 脚本不启动后端，假设后端已在 --base-url 运行；连不上时友好提示。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_BASE_URL = "http://localhost:8522"
DEFAULT_OUTPUT_DIR = "docs/screenshots"

# 页面文件名 -> 截图文件名
PAGES = [
    ("index.html", "chat.png"),
    ("manage.html", "manage.png"),
    ("feed_back.html", "feed_back.png"),
    ("use_function.html", "use_function.png"),
]


def check_backend(base_url: str) -> bool:
    """探测后端是否在运行，连不上给友好提示。"""
    try:
        with urlopen(f"{base_url}/index/", timeout=5) as resp:
            return resp.status == 200
    except (URLError, OSError, TimeoutError) as e:
        print(f"[screenshots] 无法连接后端 {base_url}: {e}", file=sys.stderr)
        print(
            "[screenshots] 请先启动后端：make dev  "
            "（或 cd backend && uv run python app/main.py）",
            file=sys.stderr,
        )
        return False


def _import_playwright():
    """延迟导入 Playwright，缺失时给安装提示而不是 ImportError 堆栈。"""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[screenshots] 未安装 Playwright，请先执行：\n"
            "  pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return None, None
    return sync_playwright, PlaywrightTimeoutError

def screenshot_chat(page, base_url: str, output: Path, timeout_error) -> None:
    """聊天页：模拟输入一条问题、点发送、等待回复到达后再截图。"""
    page.goto(f"{base_url}/web/", wait_until="networkidle", timeout=15000)
    page.wait_for_selector("#input", state="visible", timeout=10000)
    page.fill("#input", "图书馆怎么借书？")
    page.click("#submit")
    # 用户消息一定出现
    page.wait_for_selector("#chatbox .message.user", timeout=5000)
    # 判据不能用 ".message.bot .replycontent" 是否存在——首屏欢迎语和"正在思考"
    # 占位都是这个结构，选择器会立刻命中，截出来是加载态而不是回答。真正的
    # "答完了"信号是：思考指示器已从 DOM 移除，且发送按钮退出 is-loading。
    # 走完整链路（检索 + rerank + 生成）通常十几秒，给 60s 窗口。
    try:
        page.wait_for_function(
            """() => {
                const thinking = document.querySelector('.thinking-indicator');
                const submit = document.getElementById('submit');
                return !thinking && submit && !submit.classList.contains('is-loading');
            }""",
            timeout=60000,
        )
        # 追问建议在 done 事件之后单独发出，留一拍让它渲染完
        page.wait_for_timeout(1500)
    except timeout_error:
        print(
            "[screenshots] 未在 60s 内等到回复结束（LLM 可能未配置或超时），按当前状态截图",
            file=sys.stderr,
        )
        page.wait_for_timeout(800)
    output.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output), full_page=False)
    print(f"[screenshots] 已生成 {output}")


def screenshot_manage(page, base_url: str, output: Path, timeout_error) -> None:
    """管理页：等待 #index-select 加载出真实索引选项后再截图。"""
    page.goto(f"{base_url}/web/manage.html", wait_until="networkidle", timeout=15000)
    page.wait_for_selector("#index-select", state="visible", timeout=10000)
    # 等待下拉框出现非占位选项（真实索引）；3s 内没有就按当前态截
    try:
        page.wait_for_function(
            "() => { const s = document.querySelector('#index-select'); "
            "return s && s.options.length > 0 && s.options[0].value !== ''; }",
            timeout=3000,
        )
    except timeout_error:
        print("[screenshots] 管理页无可用索引，按当前态截图", file=sys.stderr)
    page.wait_for_timeout(500)
    output.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output), full_page=False)
    print(f"[screenshots] 已生成 {output}")


def screenshot_simple(page, base_url: str, page_file: str, output: Path) -> None:
    """通用截图：加载页面、等待网络空闲后直接截。"""
    page.goto(f"{base_url}/web/{page_file}", wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(800)
    output.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output), full_page=False)
    print(f"[screenshots] 已生成 {output}")

def main() -> int:
    parser = argparse.ArgumentParser(description="截取 CUITCCA 四个前端页面的 Demo 截图")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"后端地址（默认 {DEFAULT_BASE_URL}）")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"截图输出目录（默认 {DEFAULT_OUTPUT_DIR}）")
    args = parser.parse_args()

    if not check_backend(args.base_url):
        return 1

    sync_playwright, timeout_error = _import_playwright()
    if sync_playwright is None:
        return 1

    output_dir = Path(args.output_dir)
    # 逐页截图，单页失败不中断其余
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        for page_file, shot_name in PAGES:
            out_path = output_dir / shot_name
            try:
                if page_file == "index.html":
                    screenshot_chat(page, args.base_url, out_path, timeout_error)
                elif page_file == "manage.html":
                    screenshot_manage(page, args.base_url, out_path, timeout_error)
                else:
                    screenshot_simple(page, args.base_url, page_file, out_path)
            except Exception as e:
                print(f"[screenshots] 截取 {page_file} 失败：{e}", file=sys.stderr)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
