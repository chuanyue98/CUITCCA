# 可观测性（LlamaIndex Tracing）

Phase 1 接入：用 [OpenInference](https://github.com/Arize-ai/openinference) 的
`LlamaIndexInstrumentor` 把 LlamaIndex 内部每一步（retrieve、synthesize、
LLM 调用、embedding 调用）导出为 OpenTelemetry trace，通过 OTLP HTTP 协议发到
任意兼容后端——本地调试推荐 [Arize Phoenix](https://phoenix.arize.com/)，
Langfuse / OTel Collector 也吃同一个协议。

代码入口：`backend/app/configs/observability.py` 的 `init_observability()`，
在 `main.py` 的 lifespan 启动时调用一次。

## 默认关闭，零开销

不设任何环境变量时，`init_observability()` 是纯 no-op：不 import otel 包、
不注册任何 handler，只打一条 debug 日志。生产/开发都不会被 tracing 拖慢，
也不会因为没起 Phoenix 而刷连接失败的警告。

## 开启方式（环境变量）

| 变量 | 作用 |
|---|---|
| `CUITCCA_TRACING_ENABLED=true` | 显式开启。endpoint 未指定时默认发往本地 Phoenix（`http://localhost:6006/v1/traces`） |
| `OTEL_EXPORTER_OTLP_ENDPOINT=<url>` | OTLP HTTP endpoint。设置了它也视为开启（标准 OTel 变量） |
| `OTEL_SERVICE_NAME=<name>` | 可选，service.name，默认 `cuitcca` |

最常用的两种组合：

```bash
# 本地 Phoenix（默认 endpoint，最简）
CUITCCA_TRACING_ENABLED=true uv run python backend/app/main.py

# 显式指定 endpoint（Phoenix / Langfuse / Collector 均可）
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces uv run python backend/app/main.py
```

## 本地起 Phoenix（已验证可行）

以下步骤在本仓库环境实际验证过（Phoenix 17.27.0，2026-07）：

```bash
# 1. 起 Phoenix（uv 一行命令，首次运行会自动安装）
uv tool run --from arize-phoenix phoenix serve
# 首次安装 + 启动约 1 分钟；就绪后 UI 在 http://localhost:6006

# 2. 另一个终端，开着 tracing 启动应用
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:6006/v1/traces uv run python backend/app/main.py

# 3. 随便发一次查询（或跑一次评测），然后打开 http://localhost:6006 看 trace
```

不想装 uv tool 的话，docker 一行（官方镜像，未在本机验证但为官方推荐方式）：

```bash
docker run -p 6006:6006 -p 4317:4317 arizephoenix/phoenix:latest
```

验证时实际收到 trace 的确认方式（可选，纯命令行检查）：

```bash
curl -s http://localhost:6006/v1/projects
# 或 GraphQL 查 trace 数量：
curl -s -X POST http://localhost:6006/graphql -H 'Content-Type: application/json' \
  -d '{"query":"{ projects { edges { node { name traceCount } } } }"}'
```

## 能看到什么

一次检索链路产生的 span 树（实测输出，MockEmbedding 演示）：

```
VectorIndexRetriever.retrieve                 kind=RETRIEVER   (root)
└─ VectorIndexRetriever._retrieve             kind=RETRIEVER
   └─ MockEmbedding.get_query_embedding       kind=EMBEDDING
      └─ MockEmbedding._get_query_embedding   kind=EMBEDDING
```

真实问答链路里还会看到 `RouterQueryEngine`/`CondenseQuestionChatEngine` 的
CHAIN span、`OpenAILike` 的 LLM span（含完整 prompt/response、token 数）和
`HuggingFaceEmbedding` 的 EMBEDDING span，每个 span 都带
`openinference.span.kind` 属性，Phoenix UI 按 trace 聚合展示、可按延迟/错误
过滤。这正是后续 Phase 2 做检索/重排优化时定位"慢在哪、检回了什么"的依据。

## 测试

`tests/test_observability.py`：

- 未设环境变量 / 设成 falsy 时 `init_observability()` 返回 False 且不注册任何东西；
- otel 包缺失时优雅降级（warning + 返回 False），不会让应用启动崩掉；
- 注入 `InMemorySpanExporter`（测试专用参数 `span_exporter`）后，真实跑一次
  llama-index retrieve，断言产生了 RETRIEVER span 和 `openinference.span.kind`
  属性——不依赖任何外部服务；
- `shutdown_observability()` 后不再产生 span（防止 instrumentation 全局状态
  泄漏到其他测试）。
