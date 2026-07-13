"""configs/observability.py 的测试。

- 未配置环境变量时 init_observability() 必须是 no-op（返回 False、不注册任何
  instrumentation、不抛错）。
- 注入 InMemorySpanExporter 后，触发一次真实的 llama-index 检索操作
  （MockEmbedding + 内存 VectorStoreIndex，不碰网络/LLM key），必须产生 span，
  且能看到 retrieve 相关的 span。
"""
from unittest.mock import patch

import pytest

import tests._pathsetup  # noqa: F401  (adds backend/app to sys.path)


@pytest.fixture(autouse=True)
def _clean_observability_state():
    """每个测试前后重置模块级单例，避免全局 instrumentation 泄漏到其他测试。"""
    import configs.observability as obs

    obs.shutdown_observability()
    yield
    obs.shutdown_observability()


def test_init_is_noop_without_env(monkeypatch):
    import configs.observability as obs

    monkeypatch.delenv("CUITCCA_TRACING_ENABLED", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert obs.init_observability() is False
    assert obs._instrumentor is None


def test_init_is_noop_with_falsy_flag(monkeypatch):
    import configs.observability as obs

    monkeypatch.setenv("CUITCCA_TRACING_ENABLED", "false")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert obs.init_observability() is False
    assert obs._instrumentor is None


def test_init_is_idempotent_with_injected_exporter():
    import configs.observability as obs
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    assert obs.init_observability(span_exporter=exporter) is True
    # 第二次调用不重复注册
    assert obs.init_observability(span_exporter=exporter) is True
    assert obs._instrumentor is not None


def test_missing_packages_degrade_gracefully(monkeypatch):
    """otel/openinference 包 import 失败时应返回 False 而不是让启动崩掉。"""
    import builtins

    import configs.observability as obs

    monkeypatch.setenv("CUITCCA_TRACING_ENABLED", "true")

    real_import = builtins.__import__

    def _failing_import(name, *args, **kwargs):
        if name.startswith("openinference") or name.startswith("opentelemetry"):
            raise ImportError(f"simulated missing package: {name}")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=_failing_import):
        assert obs.init_observability() is False
    assert obs._instrumentor is None


def test_llama_index_retrieve_produces_spans():
    """接上 InMemorySpanExporter 后，一次真实的 llama-index 检索必须产生 span 树。

    用 MockEmbedding（不下载模型、不联网）建一个内存 VectorStoreIndex 并
    retrieve 一次——这正是线上 query 链路的第一段。
    """
    import configs.observability as obs
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.core.embeddings import MockEmbedding
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    assert obs.init_observability(span_exporter=exporter) is True

    embed_model = MockEmbedding(embed_dim=8)
    index = VectorStoreIndex.from_documents(
        [Document(text="成都信息工程大学的校训是成于大气 信达天下。")],
        embed_model=embed_model,
    )
    retriever = index.as_retriever(similarity_top_k=1)
    results = retriever.retrieve("学校的校训是什么？")
    assert len(results) == 1

    spans = exporter.get_finished_spans()
    assert spans, "instrumentation 已开启但没有产生任何 span"
    span_names = [s.name for s in spans]
    assert any("retrieve" in name.lower() for name in span_names), (
        f"span 里应包含 retrieve 相关操作，实际: {span_names}"
    )
    # OpenInference 语义约定：span 应带 openinference.span.kind 属性
    assert any(s.attributes and s.attributes.get("openinference.span.kind") for s in spans), (
        "span 缺少 openinference.span.kind 属性"
    )


def test_uninstrument_stops_span_production():
    import configs.observability as obs
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.core.embeddings import MockEmbedding
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    obs.init_observability(span_exporter=exporter)
    obs.shutdown_observability()
    exporter.clear()

    embed_model = MockEmbedding(embed_dim=8)
    index = VectorStoreIndex.from_documents([Document(text="hello")], embed_model=embed_model)
    index.as_retriever(similarity_top_k=1).retrieve("hi")

    assert exporter.get_finished_spans() == (), "uninstrument 后不应再产生 span"


def test_main_lifespan_calls_init_observability():
    """启动接线检查：main.py 的 lifespan 必须调用 init_observability。"""
    import inspect

    import main

    source = inspect.getsource(main.lifespan)
    assert "init_observability()" in source
