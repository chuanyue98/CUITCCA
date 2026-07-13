"""LlamaIndex 可观测性接入（Phase 1）。

用 OpenInference 的 LlamaIndexInstrumentor 把 LlamaIndex 内部的
retrieve / synthesize / LLM / embedding 调用导出为 OpenTelemetry trace，
发送到任意 OTLP HTTP 端点（本地 Arize Phoenix、Langfuse、OTel Collector
都吃这个协议）。使用方式见 docs/observability.md。

环境变量门控，默认完全关闭：
- CUITCCA_TRACING_ENABLED=true      显式开启（endpoint 用 OTEL_EXPORTER_OTLP_ENDPOINT，
                                    未设置时默认本地 Phoenix: http://localhost:6006/v1/traces）
- OTEL_EXPORTER_OTLP_ENDPOINT=...   设置了它也视为开启（标准 OTel 变量）

两个变量都没设时 init_observability() 是纯 no-op：不 import 任何 otel 包、
不注册任何 handler、只打一条 debug 日志，对运行时零开销。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"
_TRUTHY = ("true", "1", "t", "yes", "on")

# 幂等保护：lifespan 理论上只跑一次，但测试/reload 场景可能多次调用
_instrumentor = None


def _tracing_enabled() -> bool:
    if os.environ.get("CUITCCA_TRACING_ENABLED", "").lower() in _TRUTHY:
        return True
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))


def init_observability(span_exporter=None) -> bool:
    """初始化 LlamaIndex tracing。返回是否真的开启了。

    :param span_exporter: 测试注入口。传入一个 SpanExporter（如
        InMemorySpanExporter）时跳过环境变量门控和 OTLP exporter，直接用它；
        生产代码不要传这个参数。
    """
    global _instrumentor

    if _instrumentor is not None:
        logger.debug("observability already initialized, skipping")
        return True

    if span_exporter is None and not _tracing_enabled():
        logger.debug(
            "tracing disabled (set CUITCCA_TRACING_ENABLED=true or OTEL_EXPORTER_OTLP_ENDPOINT to enable)"
        )
        return False

    try:
        from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    except ImportError as e:
        logger.warning("tracing requested but otel/openinference packages missing: %s", e)
        return False

    resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "cuitcca")})
    tracer_provider = TracerProvider(resource=resource)

    if span_exporter is not None:
        # 测试路径：同步导出，方便断言
        tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        endpoint_desc = f"injected exporter {type(span_exporter).__name__}"
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or _DEFAULT_PHOENIX_ENDPOINT
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        endpoint_desc = endpoint

    instrumentor = LlamaIndexInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    _instrumentor = instrumentor
    logger.info("LlamaIndex tracing enabled -> %s", endpoint_desc)
    return True


def shutdown_observability() -> None:
    """卸载 instrumentation（主要给测试用，避免全局状态泄漏到其他测试）。"""
    global _instrumentor
    if _instrumentor is not None:
        try:
            _instrumentor.uninstrument()
        except Exception:
            logger.exception("failed to uninstrument LlamaIndex tracing")
        _instrumentor = None
