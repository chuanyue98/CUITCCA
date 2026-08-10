"""CUIT 站群采集 CLI：按 ``backend/app/connectors/sites.yaml`` 的配置驱动，
抓取指定站点/栏目，产出带溯源 metadata 的 Markdown 语料到 ``data/corpus/web/``。

用法示例::

    # 试跑：只看会发现多少条目、都是什么 URL，不发起详情页请求/不写文件
    uv run python scripts/crawl_cuit.py --site main --section xxjj --dry-run

    # 抓主站全部启用栏目，每个 listing 栏目最多翻 5 页（增量模式，默认行为：
    # 内容 hash 与上次一致则跳过，不重新落盘）
    uv run python scripts/crawl_cuit.py --site main --max-pages 5

    # 全量模式：忽略增量历史，强制重新抓取并覆盖已有文件
    uv run python scripts/crawl_cuit.py --site main --mode full

    # 不传 --site 时抓配置里全部 enabled 的站点
    uv run python scripts/crawl_cuit.py --max-pages 8

完整参数说明见 ``docs/data-sources.md`` 的"复现采集"一节。
"""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_APP_DIR = _REPO_ROOT / "backend" / "app"
if str(BACKEND_APP_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP_DIR))

from connectors.base import SourceRef  # noqa: E402
from connectors.config import ConfigError, ConnectorsConfig, CrawlDefaults, SiteConfig, effective_value, load_config  # noqa: E402
from connectors.markdown_io import write_markdown_file  # noqa: E402
from connectors.state import CrawlState  # noqa: E402
from connectors.web_connector import CrawlStats, WebConnector  # noqa: E402

DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "corpus" / "web"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="采集 CUIT 官网及二级站点公开信息为 Markdown 语料")
    parser.add_argument(
        "--site", action="append", dest="sites",
        help="只抓指定站点 name（可重复传递多次）。不传则抓配置里全部 enabled: true 的站点",
    )
    parser.add_argument(
        "--section", action="append", dest="sections",
        help="只抓指定栏目 name（可重复传递多次）。不传则抓所选站点下全部栏目",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="listing 类栏目的翻页深度上限，覆盖配置里的 default_max_pages（试跑时建议调小）",
    )
    parser.add_argument(
        "--mode", choices=["incremental", "full"], default="incremental",
        help="incremental（默认）：正文 hash 与上次一致则跳过；full：忽略历史记录强制重新抓取并覆盖",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只跑 discover 阶段，打印会发现多少条目，不请求详情页、不写文件、不更新增量状态",
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help=f"输出目录，默认 {DEFAULT_OUT_DIR}")
    parser.add_argument(
        "--state-file", default=None,
        help="增量状态文件路径，默认 <out-dir>/.crawl_state.json",
    )
    parser.add_argument(
        "--sites-config", default=None,
        help="覆盖默认的 sites.yaml 路径（主要给测试/自定义配置场景用）",
    )
    parser.add_argument("--verbose", action="store_true", help="打印 DEBUG 级别日志（含被跳过的 404/robots 细节）")
    return parser.parse_args(argv)


def _select_sites(config: ConnectorsConfig, requested: list[str] | None) -> list[SiteConfig]:
    if requested:
        sites = []
        for name in requested:
            site = config.get_site(name)
            if site is None:
                raise ConfigError(f"未知站点: {name!r}，配置里没有这个 name（可选值: {[s.name for s in config.sites]}）")
            sites.append(site)
        return sites
    return list(config.sites)


def _accumulate(total: CrawlStats, part: CrawlStats) -> None:
    total.discovered += part.discovered
    total.fetched += part.fetched
    total.skipped_unchanged += part.skipped_unchanged
    total.skipped_robots += part.skipped_robots
    total.failed += part.failed


def _run_site(
    site: SiteConfig,
    defaults: CrawlDefaults,
    args: argparse.Namespace,
    state: CrawlState,
    out_dir: Path,
) -> CrawlStats:
    section_names = set(args.sections) if args.sections else None
    # httpx.Client 底层连接池是线程安全的，官方推荐"一个 Client 跨多线程共用"
    # 而不是每个线程各开一个——这样连接复用（keep-alive）才有意义，也避免
    # 重复的 TLS 握手开销。
    with httpx.Client(follow_redirects=True) as client:
        connector = WebConnector(
            site,
            defaults,
            client,
            mode=args.mode,
            state=None if args.dry_run else state,
            max_pages_override=args.max_pages,
            section_names=section_names,
        )
        refs: list[SourceRef] = list(connector.discover())
        print(f"[{site.name}] discover 阶段发现 {len(refs)} 条待抓取详情页")

        if args.dry_run:
            preview = refs[:20]
            for ref in preview:
                print(f"  - [{ref.category}] {ref.identifier}")
            if len(refs) > len(preview):
                print(f"  ...(共 {len(refs)} 条，仅展示前 {len(preview)} 条)")
            return connector.stats

        max_workers = max(1, effective_value(site.max_concurrency, defaults.max_concurrency))
        written = 0
        # 并发只发生在"详情页抓取"这一层，且受限速器约束——线程池只是让多个
        # 请求的等待/解析开销可以重叠，实际发请求的节奏仍由 IntervalRateLimiter
        # 的全局间隔统一节流，两个机制不冲突：max_concurrency 管"同时有多少个
        # 请求在飞"，request_interval_seconds 管"请求发起的频率上限"。
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_ref = {pool.submit(connector.fetch, ref): ref for ref in refs}
            for i, future in enumerate(as_completed(future_to_ref), 1):
                ref = future_to_ref[future]
                try:
                    doc = future.result()
                except Exception as e:  # noqa: BLE001 - 采集脚本对单条目的任何异常都应继续处理其它条目
                    print(f"  x [{i}/{len(refs)}] {ref.identifier}: {type(e).__name__}: {e}")
                    continue
                if doc is None:
                    continue
                path = write_markdown_file(doc, out_dir)
                state.record(
                    doc.source_url,
                    content_hash=doc.content_hash,
                    output_path=str(path.relative_to(out_dir)),
                    crawled_at=doc.crawled_at,
                    title=doc.title,
                )
                written += 1
                print(f"  + [{i}/{len(refs)}] {doc.title[:40]} -> {path.name}")

        print(f"[{site.name}] 本次新写入/更新 {written} 篇文档")
        return connector.stats


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        config = load_config(args.sites_config)
    except ConfigError as e:
        print(f"[crawl] 配置错误: {e}")
        return 1

    try:
        sites = _select_sites(config, args.sites)
    except ConfigError as e:
        print(f"[crawl] {e}")
        return 1

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out_dir = Path(args.out_dir)
    state_path = Path(args.state_file) if args.state_file else out_dir / ".crawl_state.json"
    state = CrawlState.load(state_path)
    history_desc = f"已加载 {len(state)} 条历史记录" if state.loaded_from_disk else "无历史记录（全新状态文件/首次运行）"
    print(f"[crawl] 增量状态文件: {state_path} ({history_desc})")

    total_stats = CrawlStats()
    for site in sites:
        if not site.enabled:
            print(f"\n[crawl] 跳过被禁用的站点 {site.name}: {site.disabled_reason or '（未说明原因）'}")
            continue
        print(f"\n[crawl] === 站点 {site.display_name or site.name} ({site.base_url}) ===")
        try:
            stats = _run_site(site, config.defaults, args, state, out_dir)
        except ConfigError as e:
            print(f"[crawl] 站点 {site.name} 配置错误: {e}")
            continue
        _accumulate(total_stats, stats)
        print(
            f"[{site.name}] 统计: discovered={stats.discovered} fetched={stats.fetched} "
            f"skipped_unchanged={stats.skipped_unchanged} skipped_robots={stats.skipped_robots} "
            f"failed={stats.failed}"
        )

    if not args.dry_run:
        state.save()
        print(f"\n[crawl] 增量状态已保存: {state_path}（共 {len(state)} 条记录）")

    print(
        f"\n[crawl] 总计: discovered={total_stats.discovered} fetched={total_stats.fetched} "
        f"skipped_unchanged={total_stats.skipped_unchanged} skipped_robots={total_stats.skipped_robots} "
        f"failed={total_stats.failed}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
