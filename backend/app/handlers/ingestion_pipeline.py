"""基于 llama_index.core.ingestion.IngestionPipeline 的增量摄取模块（Phase 2，
去重逻辑在 code review 后于 Phase 3.1 重新设计）。

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
批文档同步进某个 collection"的场景，唯一入口是 ``ingest_files``——
``evals/ingest_corpus.py`` 就是直接调用它，不再自己手写一遍摄取流程。

## metadata: last_updated 用文件 mtime，不用摄取时间

选择文件 mtime（转成 ISO 日期字符串）而不是"这次摄取发生的时间"，原因不仅是
语义更准确（mtime 反映内容实际的最后修改时间），更关键的是技术原因：
``TextNode.hash`` 的计算包含了 ``str(metadata)``（见
``llama_index/core/schema.py:TextNode.hash``）。如果 ``last_updated`` 用"摄取
时间"，同一份内容每次重新运行摄取脚本都会因为这个字段变化而拿到不同的
hash，导致 IngestionPipeline 永远判定"内容变了"，重复重新嵌入——直接抵消了
增量摄取本来要节省的计算量。用 mtime 的话，只要文件没有被真的修改，
metadata 就是稳定的，hash 也稳定，"内容不变则跳过"才真正生效。

## 同名冲突：两层分组 + "同目录 vs 跨目录"判断

见 ``resolve_authoritative_files``。第一版实现只按 basename 分组、一律靠
mtime 挑赢家，被 code review 指出一个真实的静默丢数据问题：语料里存在
"不同来源的文档恰好同名"（比如两个八竿子打不着的院系各自维护一份
``学校历史.txt``，内容完全不同），而且这批语料是批量拷贝来的，所有文件 mtime
集中在几秒内——这种情况下"按 mtime 挑一个丢一个"本质是随机丢弃其中一份真实
内容，还给人一种"我们判断出了新旧关系"的假象。

现在的规则：

1. 按"逻辑文件名"（去掉 uuid 前缀的 basename）分组。
2. 组内再按内容 sha256 分子簇。只有 1 个子簇 -> 纯重复（多目录镜像/重复
   上传），取 mtime 最新的一份即可，这种情况下选哪份都不丢信息，安全。
3. 有多个内容不同的子簇时，看这些子簇的代表文件是否**全部来自同一个父目录**
   （``path.parent``）：
   - 是：说明大概率是"同一份文档被原地编辑/覆盖过"，按 mtime 取最新版本为
     权威源，记一条 ``ConflictResolution``（``same_directory=True``），日志
     用"采用更新版本"这种确定语气。
   - 否：说明是不同来源的文档恰好同名，**不装作能判断谁新谁旧**——全部保留，
     不丢弃任何一份。为了不让它们的 metadata ``file_name`` 撞车，这几份文档
     改用相对于语料根目录的相对路径作为逻辑标识（保留目录信息），同样记一条
     ``ConflictResolution``（``same_directory=False``），日志明确说"内容不同，
     无法判断新旧，全部保留并按路径区分"，不用"采用更新版本"这种误导性说法。

读取失败（``OSError``）的文件会被彻底排除出所有分组/hash/mtime 判断，单独
收集进返回结果里，不会静默消失，也不会意外顶替一份可用的重复文件。
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


def _distinguishing_relative_name(path: Path, corpus_root: Path | None) -> str:
    """"同名但来自不同目录、内容不同"场景下用的文档标识：保留目录信息，
    避免几份文档的 metadata file_name 撞车。"""
    if corpus_root is not None:
        try:
            return str(path.relative_to(corpus_root))
        except ValueError:
            pass
    # 没传 corpus_root，或者 path 根本不在 root 下：退化成"父目录名/文件名"，
    # 至少比裸文件名多一层区分度，也不会泄漏完整的本机绝对路径。
    return str(Path(path.parent.name) / path.name)


@dataclass
class ConflictResolution:
    """一次同名冲突的处理记录，供调用方打印/记录日志用。

    ``same_directory=True``：冲突的不同版本全部来自同一个父目录，判定为
    "同一份文档被编辑/覆盖过"，``kept_paths`` 只有一个元素（按 mtime 选出的
    权威版本），``discarded`` 是被舍弃的旧版本（连同其 mtime）。

    ``same_directory=False``：冲突的不同版本分布在不同父目录，判定为"不同
    来源的文档恰好同名"，无法判断谁新谁旧——``kept_paths`` 是全部被保留的
    文件（一个都不丢），``discarded`` 恒为空列表。
    """

    logical_name: str
    same_directory: bool
    kept_paths: list[Path]
    discarded: list[tuple[Path, float]] = field(default_factory=list)
    kept_mtime: float | None = None
    """``same_directory=True`` 时权威版本的 mtime，在挑选时就地记录（而不是
    在 ``describe()`` 里重新 ``stat()``）——避免 describe() 被调用时文件已经
    被移动/删除导致抛错，也避免重复一次没必要的系统调用。"""

    def describe(self) -> str:
        if self.same_directory:
            kept = self.kept_paths[0]
            kept_mtime = self.kept_mtime if self.kept_mtime is not None else kept.stat().st_mtime
            discarded_desc = ", ".join(
                f"{p}（mtime={datetime.fromtimestamp(m, tz=UTC).isoformat()}）" for p, m in self.discarded
            )
            return (
                f"发现同名冲突「{self.logical_name}」（同目录，判定为同一文档的不同版本）：\n"
                f"      采用更新版本 {kept}（mtime={datetime.fromtimestamp(kept_mtime, tz=UTC).isoformat()}），\n"
                f"      舍弃旧版本 {discarded_desc}"
            )
        kept_desc = "\n      ".join(str(p) for p in self.kept_paths)
        return (
            f"发现同名但来自不同目录「{self.logical_name}」：内容不同，无法判断新旧，"
            f"全部保留并按路径区分：\n      {kept_desc}"
        )


@dataclass
class ResolveResult:
    """``resolve_authoritative_files`` 的返回结果。"""

    authoritative_files: list[Path]
    conflicts: list[ConflictResolution]
    unreadable_files: list[tuple[Path, str]]
    """读取失败（OSError）、已从所有分组/hash/mtime 判断中彻底排除的文件，
    连同错误信息。不会静默消失，调用方必须打印出来。"""
    logical_names: dict[Path, str] = field(default_factory=dict)
    """path -> 应该用作 metadata file_name 的逻辑标识。多数文件不需要覆盖
    （用默认的 strip_uuid_prefix(path.name) 即可，这里就不会有对应 entry）；
    只有"同名但跨目录、内容不同"场景下被保留的文件，才会在这里映射到一个
    带目录信息的相对路径标识，避免和同名的其它文件 metadata 撞车。"""


def resolve_authoritative_files(
    file_paths: list[Path],
    corpus_root: Path | None = None,
) -> ResolveResult:
    """按"逻辑文件名"分组，组内再按内容 hash 分子簇，挑出应该摄取的权威文件。

    见模块 docstring"同名冲突：两层分组 + 同目录 vs 跨目录判断"一节。

    :param corpus_root: 语料根目录，用于给"跨目录同名冲突、全部保留"的文件
        生成保留目录信息的相对路径标识。不传时退化成"父目录名/文件名"。
    """
    groups: dict[str, list[Path]] = {}
    for path in file_paths:
        logical_name = strip_uuid_prefix(path.name)
        groups.setdefault(logical_name, []).append(path)

    authoritative: list[Path] = []
    conflicts: list[ConflictResolution] = []
    unreadable: list[tuple[Path, str]] = []
    logical_names: dict[Path, str] = {}

    for logical_name, paths in groups.items():
        if len(paths) == 1:
            authoritative.append(paths[0])
            continue

        by_hash: dict[str, list[Path]] = {}
        for path in paths:
            try:
                raw = path.read_bytes()
            except OSError as e:
                unreadable.append((path, f"{type(e).__name__}: {e}"))
                continue
            by_hash.setdefault(hashlib.sha256(raw).hexdigest(), []).append(path)

        if not by_hash:
            # 这一组里所有文件都读取失败，没有候选可挑，跳过（unreadable 里
            # 已经如实记录了每一个失败原因）。
            continue

        if len(by_hash) == 1:
            # 内容都一样：纯重复（多目录镜像/重复上传），取 mtime 最新的一份
            # 即可——只从"成功读取"的文件里选，不会被读取失败的文件顶替。
            readable_paths = next(iter(by_hash.values()))
            newest = max(readable_paths, key=lambda p: p.stat().st_mtime)
            authoritative.append(newest)
            continue

        # 真正的同名不同内容：先从每个内容子簇里选出 mtime 最新的代表
        # （这一步只在"内容相同"的文件之间比较，不会丢信息）。
        representatives = [max(group, key=lambda p: p.stat().st_mtime) for group in by_hash.values()]
        parent_dirs = {rep.parent for rep in representatives}

        if len(parent_dirs) == 1:
            # 都在同一目录：判定为"同一文档被编辑过"，按 mtime 取新版本
            representatives.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            winner, losers = representatives[0], representatives[1:]
            winner_mtime = winner.stat().st_mtime
            authoritative.append(winner)
            conflicts.append(
                ConflictResolution(
                    logical_name=logical_name,
                    same_directory=True,
                    kept_paths=[winner],
                    discarded=[(p, p.stat().st_mtime) for p in losers],
                    kept_mtime=winner_mtime,
                )
            )
        else:
            # 分布在不同目录：不同来源恰好同名，不装作能判断新旧，全部保留，
            # 用相对路径区分身份，避免 metadata file_name 撞车。
            authoritative.extend(representatives)
            for rep in representatives:
                logical_names[rep] = _distinguishing_relative_name(rep, corpus_root)
            conflicts.append(
                ConflictResolution(
                    logical_name=logical_name,
                    same_directory=False,
                    kept_paths=list(representatives),
                    discarded=[],
                )
            )

    return ResolveResult(
        authoritative_files=authoritative,
        conflicts=conflicts,
        unreadable_files=unreadable,
        logical_names=logical_names,
    )


def documents_from_file(file_path: Path, logical_name: str | None = None) -> list[Document]:
    """把一个文件读成 Document 列表：doc_id = 内容 sha256，metadata 带
    ``file_name``（逻辑文件名，见下）和 ``last_updated``（文件 mtime 的
    ISO 日期，见模块 docstring 里为什么不用摄取时间）。

    :param logical_name: 显式指定 metadata 里的 file_name。不传则用默认的
        ``strip_uuid_prefix(file_path.name)``——只有 ``resolve_authoritative_files``
        判定为"跨目录同名冲突"的文件才需要传这个参数（用带目录信息的相对
        路径，避免撞车）。
    """
    docs = SimpleDirectoryReader(input_files=[str(file_path)]).load_data()
    mtime = file_path.stat().st_mtime
    last_updated = datetime.fromtimestamp(mtime, tz=UTC).date().isoformat()
    resolved_logical_name = logical_name if logical_name is not None else strip_uuid_prefix(file_path.name)

    out = []
    for doc in docs:
        text = doc.get_content()
        doc_id = content_hash(text)
        doc.doc_id = doc_id
        doc.id_ = doc_id
        doc.metadata["file_name"] = resolved_logical_name
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
    unreadable_files: list[tuple[Path, str]]
    empty_files: list[Path]
    parse_failures: list[tuple[Path, str]]
    documents_loaded: int
    nodes_upserted: int
    doc_id_to_paths: dict[str, list[Path]]
    """内容 hash（doc_id） -> 产生这个 doc_id 的所有来源文件路径。通常只有
    1 个；如果两个逻辑文件名不同的文件内容恰好完全相同，
    resolve_authoritative_files 的同名分组不会捕捉到这种情况（分组本来就是
    按名字来的），两个路径都会走到这里、映射到同一个 doc_id——用 list 而不是
    覆盖式的单值 dict，确保这种情况下两个文件名都会出现在最终报告里，不会
    因为后写入覆盖先写入而悄悄丢失一个。"""
    nodes_by_doc_id: dict[str, int]
    """doc_id -> 本次实际写入的 chunk/node 数量。配合 doc_id_to_paths 可以
    推出"这些文件（可能不止一个文件名）一共贡献了多少 chunk"。"""


def ingest_files(
    file_paths: list[Path],
    pipeline: IngestionPipeline,
    resolve_conflicts: bool = True,
    corpus_root: Path | None = None,
) -> IngestResult:
    """把一批文件同步进 pipeline 关联的 vector_store。这是本模块唯一的批量
    摄取入口——调用方（比如 evals/ingest_corpus.py）应该直接用这个函数，
    不要自己再手写一遍"消解冲突 -> 解析 -> pipeline.run"的流程。

    :param resolve_conflicts: 是否先跑 ``resolve_authoritative_files`` 做同名
        冲突消解。默认开。调用方如果已经自己做过这一步（比如上游已保证文件名
        唯一），可以传 False 跳过。
    :param corpus_root: 透传给 ``resolve_authoritative_files``，用于跨目录同名
        冲突时生成带目录信息的相对路径标识。
    """
    conflicts: list[ConflictResolution] = []
    unreadable: list[tuple[Path, str]] = []
    logical_names: dict[Path, str] = {}
    resolved_paths = file_paths

    if resolve_conflicts:
        resolve_result = resolve_authoritative_files(file_paths, corpus_root=corpus_root)
        resolved_paths = resolve_result.authoritative_files
        conflicts = resolve_result.conflicts
        unreadable = resolve_result.unreadable_files
        logical_names = resolve_result.logical_names

    parse_failures: list[tuple[Path, str]] = []
    empty_files: list[Path] = []
    documents: list[Document] = []
    doc_id_to_paths: dict[str, list[Path]] = {}

    for path in resolved_paths:
        try:
            docs = documents_from_file(path, logical_name=logical_names.get(path))
        except Exception as e:
            parse_failures.append((path, f"{type(e).__name__}: {e}"))
            continue

        docs = [d for d in docs if d.get_content().strip()]
        if not docs:
            empty_files.append(path)
            continue

        for doc in docs:
            doc_id_to_paths.setdefault(doc.doc_id, []).append(path)
        documents.extend(docs)

    nodes = pipeline.run(documents=documents) if documents else []

    nodes_by_doc_id: dict[str, int] = {}
    for node in nodes:
        ref_id = node.ref_doc_id or node.id_
        nodes_by_doc_id[ref_id] = nodes_by_doc_id.get(ref_id, 0) + 1

    return IngestResult(
        candidate_files=len(file_paths),
        conflicts=conflicts,
        unreadable_files=unreadable,
        empty_files=empty_files,
        parse_failures=parse_failures,
        documents_loaded=len(documents),
        nodes_upserted=len(nodes),
        doc_id_to_paths=doc_id_to_paths,
        nodes_by_doc_id=nodes_by_doc_id,
    )
