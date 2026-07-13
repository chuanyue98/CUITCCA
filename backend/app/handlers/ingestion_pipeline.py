"""基于 llama_index.core.ingestion.IngestionPipeline 的增量摄取模块（Phase 2）。

替代"整库重建"式摄取的新能力：文档 id 按内容 sha256 生成（不用文件名，更不用
router/index.py 上传时加的随机 uuid 前缀），配合 IngestionPipeline 的
DocstoreStrategy.UPSERTS，让重复运行天然具备：

- 内容完全相同 -> 同一个 doc_id、同一份内容 hash（llama_index 的
  ``TextNode.hash`` = sha256(text + str(metadata))）-> pipeline 判定"文档已存
  在且哈希未变" -> 跳过，不重新切块/嵌入。
- 内容变化（同一 doc_id 出现新内容） -> 哈希不同 -> 删除旧 node、重新嵌入。
- 全新内容 -> 新增。

这是一个独立可调用模块，**目前不替换** ``handlers/index_crud.py`` 里现有的
``insert_into_index`` 调用链路——那条链路被 30+ 现有测试、``router/index.py``
的上传接口和线上流程依赖，直接替换收益（增量去重）相对上传场景（单文件、
用户主动点击上传）不明显，但破坏范围很大，不划算。本模块面向"批量/定期把一
批文档同步进某个 collection"的场景（比如 evals/ingest_corpus.py，未来的
后台批量导入工具），可以直接调用这里的 ``ingest_files``。

## metadata: last_updated 用文件 mtime，不用摄取时间

选择文件 mtime（转成 ISO 日期字符串）而不是"这次摄取发生的时间"，原因不仅是
语义更准确（mtime 反映内容实际的最后修改时间），更关键的是技术原因：
``TextNode.hash`` 的计算包含了 ``str(metadata)``（见
``llama_index/core/schema.py:TextNode.hash``）。如果 ``last_updated`` 用"摄取
时间"，同一份内容每次重新运行摄取脚本都会因为这个字段变化而拿到不同的
hash，导致 IngestionPipeline 永远判定"内容变了"，重复重新嵌入——直接抵消了
增量摄取本来要节省的计算量。用 mtime 的话，只要文件没有被真的修改，
metadata 就是稳定的，hash 也稳定，"内容不变则跳过"才真正生效。

## 同名不同内容冲突：按 mtime 取更新版本

见 ``resolve_authoritative_files``：源语料里发现过同名但内容不同的文件（如
两个版本的 ``学校历史.txt``、``历任领导.txt``），这种情况没法靠内容 hash
解决（hash 本来就不同）。规则是取 mtime 更新的版本作为权威源，理由是 mtime
更新大概率代表"后来修订/勘误过"的内容，比"哪个文件先被目录扫描到"更能代表
当前真实状态。旧版本不会被静默丢弃——调用方必须打印/记录冲突详情（哪个被
采用、哪个被舍弃），保证信息不会无声消失，只是不参与本次摄取。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from llama_index.core import Settings, SimpleDirectoryReader
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.ingestion import DocstoreStrategy, IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.storage.docstore.types import BaseDocumentStore
from llama_index.core.vector_stores.types import BasePydanticVectorStore

# 上传时（router/index.py: f"{uuid.uuid4()}_{filename}"）加的 uuid4 前缀。
# 摄取管道内部按"逻辑文件名"（去掉这个前缀）识别"这其实是同一份文档"，
# 不被 uuid 前缀污染成分文件名都不同的对象。
_UUID_PREFIX_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}_"
)


def strip_uuid_prefix(file_name: str) -> str:
    """去掉上传时自动加的 uuid4 前缀，还原成"逻辑文件名"。"""
    if not file_name:
        return file_name
    return _UUID_PREFIX_RE.sub("", file_name)


def content_hash(text: str) -> str:
    """内容 sha256（十六进制），用作文档的确定性 doc_id。

    同样的文本，无论来自哪个文件名/哪次上传，都会得到同一个 id，这是让
    IngestionPipeline 的 UPSERTS 策略能跨"不同文件名、相同内容"识别重复的
    关键——不这么做的话，dedup 是按 ref_doc_id 比较的，两次上传同一份内容
    但文件名（doc_id）不同，会被当成两份不同文档，各自嵌入一次。
    """
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


@dataclass
class ConflictResolution:
    """一次"同名不同内容"冲突的解决记录，供调用方打印/记录日志用。"""

    logical_name: str
    kept_path: Path
    kept_mtime: float
    discarded: list[tuple[Path, float]] = field(default_factory=list)

    def describe(self) -> str:
        discarded_desc = ", ".join(
            f"{p}（mtime={datetime.fromtimestamp(m, tz=UTC).isoformat()}）" for p, m in self.discarded
        )
        return (
            f"发现同名冲突「{self.logical_name}」：采用更新版本 {self.kept_path}"
            f"（mtime={datetime.fromtimestamp(self.kept_mtime, tz=UTC).isoformat()}），"
            f"舍弃旧版本 {discarded_desc}"
        )


def resolve_authoritative_files(file_paths: list[Path]) -> tuple[list[Path], list[ConflictResolution]]:
    """按"逻辑文件名"（去掉 uuid 前缀后的 basename）分组，挑出每组的权威文件。

    - 组内只有一个文件：直接保留。
    - 组内多个文件但内容 hash 全部相同：纯粹是重复上传/多目录镜像，不算冲突，
      取 mtime 最新的一份（谁被留下不影响内容，选最新只是让 last_updated 更
      准确）。
    - 组内存在不同内容的 hash（真正的"同名不同内容"）：每个不同内容版本先各
      选出该版本里 mtime 最新的代表，再从这些代表里选 mtime 最新的作为权威
      版本；其余记为一条 ``ConflictResolution``，供调用方打日志，不静默丢弃。

    返回 (应该摄取的文件列表, 冲突记录列表)。
    """
    groups: dict[str, list[Path]] = {}
    for path in file_paths:
        logical_name = strip_uuid_prefix(path.name)
        groups.setdefault(logical_name, []).append(path)

    authoritative: list[Path] = []
    conflicts: list[ConflictResolution] = []

    for logical_name, paths in groups.items():
        if len(paths) == 1:
            authoritative.append(paths[0])
            continue

        by_hash: dict[str, list[Path]] = {}
        for path in paths:
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            by_hash.setdefault(hashlib.sha256(raw).hexdigest(), []).append(path)

        if len(by_hash) <= 1:
            # 内容都一样：纯重复，取 mtime 最新的一份
            newest = max(paths, key=lambda p: p.stat().st_mtime)
            authoritative.append(newest)
            continue

        # 真正的同名不同内容冲突
        representatives = [max(group, key=lambda p: p.stat().st_mtime) for group in by_hash.values()]
        representatives.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        winner, losers = representatives[0], representatives[1:]
        authoritative.append(winner)
        conflicts.append(
            ConflictResolution(
                logical_name=logical_name,
                kept_path=winner,
                kept_mtime=winner.stat().st_mtime,
                discarded=[(p, p.stat().st_mtime) for p in losers],
            )
        )

    return authoritative, conflicts


def documents_from_file(file_path: Path) -> list[Document]:
    """把一个文件读成 Document 列表：doc_id = 内容 sha256，metadata 带
    ``file_name``（逻辑文件名，不含 uuid 前缀）和 ``last_updated``（文件 mtime
    的 ISO 日期，见模块 docstring 里为什么不用摄取时间）。
    """
    docs = SimpleDirectoryReader(input_files=[str(file_path)]).load_data()
    mtime = file_path.stat().st_mtime
    last_updated = datetime.fromtimestamp(mtime, tz=UTC).date().isoformat()
    logical_name = strip_uuid_prefix(file_path.name)

    out = []
    for doc in docs:
        text = doc.get_content()
        doc_id = content_hash(text)
        doc.doc_id = doc_id
        doc.id_ = doc_id
        doc.metadata["file_name"] = logical_name
        doc.metadata["last_updated"] = last_updated
        out.append(doc)
    return out


def build_pipeline(
    vector_store: BasePydanticVectorStore,
    docstore: BaseDocumentStore | None = None,
    docstore_strategy: DocstoreStrategy = DocstoreStrategy.UPSERTS,
    chunk_size: int | None = None,
    embed_model: BaseEmbedding | None = None,
) -> IngestionPipeline:
    """构建增量摄取用的 IngestionPipeline。

    :param vector_store: 目标向量库（如 ChromaVectorStore(chroma_collection=...)）。
    :param docstore: 记录"doc_id -> 内容 hash"的文档存储，UPSERTS 策略靠它判断
        跳过/更新/新增。不传则用内存态 ``SimpleDocumentStore``（进程重启后就
        丢失增量记忆，仅适合单次运行场景；需要跨进程/跨运行保留增量能力的
        调用方应传入持久化的 docstore，比如
        ``SimpleDocumentStore.from_persist_path(path)`` 加载、结束后
        ``docstore.persist(path)``）。
    :param chunk_size: 切块大小。不传则用 ``SentenceSplitter.from_defaults()``
        的默认值（1024），与现有 ``utils/llama.py:get_nodes_from_file``（线上
        插入路径）保持一致，避免引入不一致的分块粒度。
    :param embed_model: 显式传入 embedding 模型（比如测试里传 MockEmbedding，
        避免测试触碰全局 ``Settings.embed_model`` 单例、在没配置的进程里触发
        它去尝试解析 OpenAI embedding 报错）。不传则在调用时读取
        ``Settings.embed_model``（线上/评测脚本走这条路，与
        ``configs/llm_predictor.py:init_settings`` 配置的 bge-m3 一致）。
    """
    splitter = SentenceSplitter.from_defaults(chunk_size=chunk_size) if chunk_size else SentenceSplitter.from_defaults()
    resolved_embed_model = embed_model if embed_model is not None else Settings.embed_model
    return IngestionPipeline(
        transformations=[splitter, resolved_embed_model],
        docstore=docstore if docstore is not None else SimpleDocumentStore(),
        vector_store=vector_store,
        docstore_strategy=docstore_strategy,
    )


@dataclass
class IngestResult:
    """一次 ``ingest_files`` 调用的统计结果。"""

    candidate_files: int
    conflicts: list[ConflictResolution]
    parse_failures: list[tuple[Path, str]]
    documents_loaded: int
    nodes_upserted: int
    """本次实际重新切块/嵌入的 node 数（未变化被跳过的文档不计入）。"""


def ingest_files(
    file_paths: list[Path],
    pipeline: IngestionPipeline,
    resolve_conflicts: bool = True,
) -> IngestResult:
    """把一批文件同步进 pipeline 关联的 vector_store。

    :param resolve_conflicts: 是否先跑 ``resolve_authoritative_files`` 做同名
        冲突消解。默认开。调用方如果已经自己做过这一步（比如上游已保证文件名
        唯一），可以传 False 跳过。
    """
    conflicts: list[ConflictResolution] = []
    resolved_paths = file_paths
    if resolve_conflicts:
        resolved_paths, conflicts = resolve_authoritative_files(file_paths)

    parse_failures: list[tuple[Path, str]] = []
    documents: list[Document] = []
    for path in resolved_paths:
        try:
            documents.extend(documents_from_file(path))
        except Exception as e:
            parse_failures.append((path, f"{type(e).__name__}: {e}"))

    nodes = pipeline.run(documents=documents) if documents else []

    return IngestResult(
        candidate_files=len(file_paths),
        conflicts=conflicts,
        parse_failures=parse_failures,
        documents_loaded=len(documents),
        nodes_upserted=len(nodes),
    )
