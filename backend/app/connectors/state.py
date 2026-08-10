"""增量抓取状态：记录"这个 URL 上次抓到的正文 hash 是什么"，下次抓取内容
没变就跳过，不重新写文件、不重新占用带宽。

思路和 ``handlers/ingestion_pipeline.py`` 的 ``content_hash()``
（sha256 判重做 doc_id）一致，但这里状态要跨"进程/多次运行"持久化——摄取
管道的 hash 判重靠 IngestionPipeline 自带的 docstore，连接器这边没有那套
基础设施，所以自己维护一个轻量的 JSON 状态文件，字段只保留判重和排障必需
的最小集合。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class UrlState:
    content_hash: str
    output_path: str
    """产出的语料文件路径（相对 state 文件所在目录），排障时能直接定位到
    "这个 URL 上次写到了哪个文件"。"""
    last_crawled_at: str
    """最近一次成功抓取（无论内容是否变化）的时间，ISO 8601。"""
    title: str = ""
    """冗余存一份标题，纯粹方便人工打开 state 文件时肉眼核对，不参与判重
    逻辑。"""


class CrawlState:
    """URL -> UrlState 的状态存取，读写一个 JSON 文件。

    没有用 sqlite/其他数据库——量级上几千个 URL 的 JSON 完全够用还便于
    人工检查/版本对比，引入数据库对这个场景是过度设计。
    """

    def __init__(self, path: Path):
        self._path = path
        self._entries: dict[str, UrlState] = {}
        self._loaded_from_disk = False

    @classmethod
    def load(cls, path: Path) -> CrawlState:
        state = cls(path)
        state._load()
        return state

    def _load(self) -> None:
        if not self._path.is_file():
            self._loaded_from_disk = False
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 状态文件损坏/读取失败：视为"没有历史状态"从头开始，而不是让
            # 整次抓取直接崩溃——增量抓取退化成全量抓取是可接受的降级，比
            # 无法运行更好。
            self._entries = {}
            self._loaded_from_disk = False
            return
        self._entries = {url: UrlState(**fields) for url, fields in raw.items()}
        self._loaded_from_disk = True

    @property
    def loaded_from_disk(self) -> bool:
        return self._loaded_from_disk

    def get(self, url: str) -> UrlState | None:
        return self._entries.get(url)

    def is_unchanged(self, url: str, content_hash: str) -> bool:
        """判断某 URL 的正文相对上次抓取是否没变——增量模式下调用方据此决定
        要不要跳过重新落盘。"""
        prev = self._entries.get(url)
        return prev is not None and prev.content_hash == content_hash

    def record(self, url: str, *, content_hash: str, output_path: str, crawled_at: str, title: str = "") -> None:
        self._entries[url] = UrlState(
            content_hash=content_hash,
            output_path=output_path,
            last_crawled_at=crawled_at,
            title=title,
        )

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {url: asdict(state) for url, state in sorted(self._entries.items())}
        # 先写临时文件再原子替换，避免抓到一半进程被杀掉时留下一个截断/
        # 损坏的 state 文件（那样下次会误判成"什么都没抓过"，退化成全量重抓，
        # 虽不算严重故障但没必要冒这个险，加一步 rename 几乎零成本）。
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)

    def __len__(self) -> int:
        return len(self._entries)
