# 校园AI助手 (CUIT Campus AI Assistant)

基于 FastAPI + LlamaIndex 的校园智能问答系统，采用 RAG（检索增强生成）架构，支持文档上传、知识库管理、混合检索与多轮流式对话。

## 核心特性

- **RAG 问答**: 基于文档索引的智能问答，检索层默认启用 BM25(jieba分词) + 向量 RRF 混合检索与条件触发式 cross-encoder rerank
- **增量摄取去重**: 上传文档按内容 sha256 去重（UPSERTS），内容不变的重复上传直接跳过、内容变化原地更新
- **多轮流式对话**: 基于 `/graph/chat_stream` 实现 token 级流式输出，支持连续追问与上下文记忆
- **Markdown 渲染**: 回答使用 marked.js + DOMPurify 渲染并净化，命中知识库时展示可展开的参考来源
- **对话历史持久化**: 对话记录保存在浏览器 `localStorage`，刷新自动恢复
- **暗色模式**: 跟随系统 `prefers-color-scheme` 自动切换，覆盖全部页面
- **知识库管理**: 创建/删除索引，上传文档（PDF/DOCX/TXT/MD/CSV/XLSX），增删节点
- **安全防护**: API Key 认证、速率限制、路径穿越防护、时序安全比较

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python 3.12+, FastAPI, Uvicorn |
| AI 框架 | LlamaIndex (Workflow, RetrieverQueryEngine, RouterRetriever) |
| 向量存储 | ChromaDB |
| 嵌入模型 | HuggingFace Embeddings |
| 重排序 | sentence-transformers (BAAI/bge-reranker-v2-m3) |
| 混合检索 | bm25s + jieba 分词, RRF 融合 |
| 数据库 | SQLite (访问统计与用户反馈) |
| 前端 | TypeScript, Vite, HTML/CSS (无框架), marked.js + DOMPurify |
| 包管理 | uv |
| 测试 | pytest, pytest-asyncio, pytest-cov |
| CI/CD | GitHub Actions, Dependabot |

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                     客户端 (浏览器)                       │
│  index.html (聊天)  manage.html (管理)  feed_back.html   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────────────┐
│                  FastAPI 应用 (main.py)                  │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  中间件层                                            │ │
│  │  • 会话管理 (Cookie session_id)                     │ │
│  │  • 速率限制 (30 req / 60s / IP)                     │ │
│  │  • 访问统计 (异步锁保护)                              │ │
│  │  • CORS                                             │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  路由层                                              │ │
│  │  /index   → 索引 CRUD、文档上传、QA 生成             │ │
│  │  /graph   → 查询、流式聊天、WebSocket                │ │
│  │  /manage  → 统计、反馈、环境配置 (需 API Key)         │ │
│  │  /response→ 自定义响应模式查询                        │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  处理层 (Handlers)                                   │ │
│  │  • QAWorkflow: condense → retrieve → synthesize     │ │
│  │  • HybridRetriever: BM25 + Dense (RRF 融合)         │ │
│  │  • IngestionPipeline: UPSERTS 去重摄取               │ │
│  │  • ConditionalRerankPostprocessor: 条件触发重排      │ │
│  └─────────────────────────────────────────────────────┘ │
└───────────┬───────────────────────┬─────────────────────┘
            │                       │
   ┌────────▼────────┐    ┌────────▼────────┐
   │   ChromaDB      │    │    SQLite       │
   │ (向量存储/检索)  │    │ (统计/反馈)     │
   └─────────────────┘    └─────────────────┘
```

### QAWorkflow 流程

```
StartEvent
    │
    ▼
condense_question step
    │  (单轮: 直接透传 / 多轮: LLM 压缩追问为独立问题)
    ▼
retrieve step
    │  (0索引: 空检索器 / 1索引: 直接检索 / 多索引: RouterRetriever)
    │  (检索后: ConditionalRerankPostprocessor 条件触发重排)
    ▼
synthesize step
    │  (流式: astream_chat + TokenEvent / 非流式: achat)
    ▼
StopEvent (response + source_nodes)
```

## 快速开始

### 前置要求

- Python >= 3.12
- [uv](https://github.com/astral-sh/uv) 包管理器
- Node.js >= 18 (前端开发，可选)

### 安装与运行

```bash
# 1. 克隆仓库
git clone https://github.com/ChuanYuei/CUITCCA.git
cd CUITCCA

# 2. 安装依赖
uv sync

# 3. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入 OPENAI_API_KEY 等配置

# 4. 启动后端
cd backend
uv run python app/main.py
# 或使用 Makefile: make dev (热重载) / make run (生产)
```

服务启动后访问 `http://localhost:8522/web/` 即可使用前端界面。

### 前端开发 (可选)

```bash
cd frontend
npm install
npm run dev    # 开发服务器 (Vite)
npm run build  # 构建生产产物
```

## 环境变量配置

在 `backend/.env` 中配置以下变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | (必填) | LLM API 密钥 |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | LLM API 地址 |
| `OPENAI_MODEL` | `sensenova-6.7-flash-lite` | 使用的模型名称 |
| `CUITCCA_API_KEY` | (空) | 管理接口认证密钥，为空时管理接口返回 503 |
| `HOST` | `0.0.0.0` | 服务绑定地址 |
| `PORT` | `8522` | 服务端口 |
| `COOKIE_SECURE` | `False` | Cookie Secure 标志 |
| `COOKIE_MAX_AGE` | `86400` | Cookie 有效期（秒） |
| `CORS_ORIGINS` | (localhost) | 允许的 CORS 源（逗号分隔） |
| `VERBOSE` | `False` | 详细日志输出 |

### 检索配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SIMILARITY_TOP_K` | `5` | 主查询路径默认 top_k |
| `QUERY_ENDPOINT_TOP_K` | `2` | /index/{name}/query 接口的 top_k |
| `MULTI_INDEX_FALLBACK_TOP_K` | `3` | 多索引回退 top_k |
| `HYBRID_RETRIEVAL_ENABLED` | `True` | 混合检索开关 (BM25 + Dense RRF) |
| `RERANK_ENABLED` | `True` | 条件触发式 rerank 开关 |
| `RERANK_RECALL_K` | `20` | Rerank 候选召回数 |
| `RERANK_TOP_N` | `5` | Rerank 后保留的 top N |
| `RERANK_SCORE_THRESHOLD` | `0.75` | Top1 分数高于此值时跳过 rerank |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | 重排序模型 |

### 存储路径配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `INDEX_SAVE_DIRECTORY` | `../../data/indexes/` | 索引持久化目录 |
| `SAVE_PATH` | `../../data/upload_files` | 上传文件永久存储 |
| `LOAD_PATH` | `../../data/temp/` | 上传临时目录 |
| `CHROMA_DB_PATH` | `../../data/chroma_db/` | ChromaDB 数据目录 |
| `DB_PATH` | `../../data/app.db` | SQLite 数据库路径 |

## API 参考

### 索引管理 (`/index`)

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/index/` | GET | 健康检查 | 无 |
| `/index/list` | GET | 列出所有索引 | 无 |
| `/index/create` | POST | 创建新索引 | 无 |
| `/index/delete` | POST | 删除索引 | 无 |
| `/index/{name}/info` | GET | 获取索引文档列表 | 无 |
| `/index/{name}/query` | POST | 查询索引 | 无 |
| `/index/{name}/uploadFile` | POST | 上传单个文件 | 无 |
| `/index/{name}/uploadFiles` | POST | 批量上传文件 | 无 |
| `/index/{name}/upload_file_by_QA` | POST | 从文件生成 QA 对 | 无 |
| `/index/{name}/insertdoc` | POST | 插入文本文档 | 无 |
| `/index/{name}/deleteDoc` | POST | 按文档 ID 删除 | 无 |
| `/index/{name}/deleteNode` | POST | 按节点 ID 删除 | 无 |
| `/index/{name}/update` | POST | 更新节点内容 | 无 |
| `/index/{name}/get_summary` | GET | 获取索引摘要 | 无 |
| `/index/{name}/set_summary` | POST | 设置索引摘要 | 无 |
| `/index/{name}/generate_summary` | POST | AI 生成摘要 | 无 |
| `/index/{name}/getfile` | POST | 导出索引内容 | 无 |
| `/index/{name}/evaluator` | POST | 评估查询响应 | 无 |
| `/index/{name}/save` | POST | 保存索引 | 无 |

### 图查询与聊天 (`/graph`)

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/graph/query` | POST | 非流式查询 | 无 |
| `/graph/query_stream` | POST | 流式查询 (SSE) | 无 |
| `/graph/chat_stream` | POST | 多轮流式聊天 | 无 |
| `/graph/query_sources` | POST | 获取上次查询来源 | 无 |
| `/graph/query_history` | POST | 获取聊天历史 | 无 |
| `/graph/create` | POST | 创建新会话 | 无 |
| `/graph/agent` | POST | Agent 查询 | 无 |
| `/graph/query` | WS | WebSocket 查询 | API Key |
| `/graph/workflow_query` | POST | Workflow 查询 | 无 |
| `/graph/workflow_query_stream` | POST | Workflow 流式查询 | 无 |

### 管理接口 (`/manage`)

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/manage/stats` | GET | 获取访问统计 | API Key |
| `/manage/feedback` | POST | 提交反馈 | API Key |
| `/manage/feedback` | GET | 列出反馈 | API Key |
| `/manage/env` | POST | 更新 LLM 环境变量 | API Key |

### 响应查询 (`/response`)

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/response/{name}/query` | POST | 自定义响应模式查询 | 无 |

## 项目结构

```
CUITCCA/
├── backend/
│   └── app/
│       ├── main.py                  # 应用入口、中间件、速率限制
│       ├── configs/
│       │   ├── config.py            # Prompt 模板、响应模式枚举
│       │   ├── llm_predictor.py     # LLM 构建与初始化
│       │   ├── load_env.py          # 环境变量加载与热重载
│       │   └── observability.py     # OpenTelemetry 可观测性
│       ├── router/
│       │   ├── index.py             # 索引管理路由
│       │   ├── graph.py             # 查询与聊天路由
│       │   ├── manage.py            # 管理接口路由
│       │   └── response.py          # 自定义响应查询
│       ├── handlers/
│       │   ├── qa_workflow.py       # QA 工作流 (condense→retrieve→synthesize)
│       │   ├── hybrid_retriever.py  # 混合检索 (BM25+Dense RRF)
│       │   ├── index_crud.py        # 索引 CRUD 与文档操作
│       │   ├── ingestion_pipeline.py # 增量摄取管道 (UPSERTS)
│       │   ├── vector_store.py      # ChromaDB 向量存储
│       │   ├── graph_builder.py     # 索引摘要生成
│       │   └── llama_handler.py     # Prompt 查找
│       ├── dependencies/
│       │   ├── index_dep.py         # 索引依赖注入
│       │   └── manage.py            # 访问统计与锁
│       ├── models/
│       │   ├── response.py          # 响应模型
│       │   └── user.py              # 用户反馈模型
│       ├── utils/
│       │   ├── security.py          # API Key 认证、IP 获取
│       │   ├── file.py              # 文件解析 (PDF/DOCX/XLSX/TXT)
│       │   ├── upload.py            # 上传验证
│       │   ├── db.py                # SQLite 操作
│       │   ├── llama.py             # LlamaIndex 工具函数
│       │   ├── rerank.py            # 条件触发式重排序
│       │   └── logger.py            # 日志配置
│       ├── exceptions/
│       │   └── llama_exception.py   # LLM 异常处理
│       └── static/                  # 前端静态文件 (备用)
├── frontend/
│   ├── index.html                   # 聊天页面
│   ├── manage.html                  # 知识库管理
│   ├── feed_back.html               # 反馈页面
│   ├── use_function.html            # 使用指南
│   ├── style.css                    # 全局样式
│   ├── src/
│   │   ├── chat.ts                  # 聊天逻辑
│   │   ├── manage.ts                # 管理逻辑
│   │   ├── sidebar.ts               # 侧边栏组件
│   │   └── feedback.ts             # 反馈逻辑
│   └── vendor/                      # 第三方库 (本地)
├── tests/                           # pytest 测试 (314 tests, 95% coverage)
├── evals/                           # 检索评测脚本
├── data/                            # 数据存储
│   ├── chroma_db/                   # ChromaDB 持久化
│   ├── indexes/                     # 索引文件
│   ├── upload_files/                # 上传文件
│   └── app.db                       # SQLite 数据库
├── docs/                            # 开发文档
├── .github/workflows/               # CI/CD
├── pyproject.toml                   # 项目依赖与工具配置
├── Makefile                         # 开发命令
├── backend.bash                     # Linux 启动脚本
└── backend.bat                      # Windows 启动脚本
```

## 运行测试

```bash
# 运行全部测试
uv run pytest tests/ -v

# 运行测试并生成覆盖率报告
uv run pytest tests/ -v --cov=backend/app --cov-report=term

# 运行特定测试文件
uv run pytest tests/test_xlsx_parser.py -v

# 跳过评测测试
uv run pytest tests/ -m "not eval"
```

当前测试状态：314 个测试全部通过，覆盖率 95.31%。

## 开发命令

```bash
make dev        # 启动开发服务器（热重载）
make run        # 启动生产服务器
make test       # 运行测试
make lint       # 代码风格检查 (ruff)
make typecheck  # 类型检查 (mypy)
make security   # 安全扫描 (pip-audit + bandit)
make format     # 自动格式化
make clean      # 清理缓存
make frontend-install  # 安装前端依赖
make frontend-dev     # 启动前端开发服务器
make frontend-build   # 构建前端
```

## 安全设计

- **API Key 认证**: 管理接口需要 Bearer token 认证，使用 `secrets.compare_digest` 防止时序攻击
- **速率限制**: LLM 查询端点限制每 IP 每 60 秒 30 次请求，超出返回 429
- **路径穿越防护**: `safe_filename` 函数去除路径分隔符，防止 `../../` 攻击
- **IP 安全**: 仅信任 `request.client.host`，不信任 `X-Real-IP` / `X-Forwarded-For` 等可伪造 header
- **WebSocket 认证**: WebSocket 连接需要 `?token=` 参数验证 API Key，未配置时拒绝连接
- **错误信息安全**: 错误消息不泄露文件路径或内部细节
- **输入长度限制**: 查询输入限制 5000 字符，表单字段均有 `max_length` 限制
- **文件类型白名单**: 仅允许 PDF、DOCX、TXT、MD、CSV、XLSX 文件上传

## 检索架构

### 混合检索 (BM25 + Dense RRF)

默认开启（`HYBRID_RETRIEVAL_ENABLED=True`），使用 jieba 分词构建 BM25 索引，与向量检索结果通过 RRF (Reciprocal Rank Fusion) 融合。评测数据：hit@1 +10pp, MRR +0.04, 延迟仅增加约 2ms。

### 条件触发式 Rerank

默认开启（`RERANK_ENABLED=True`），仅当向量检索 top1 分数低于阈值（`RERANK_SCORE_THRESHOLD=0.75`）时才触发 cross-encoder 重排序。评测数据：hit@1 +15pp, MRR +0.06, 延迟约 660ms (CPU)，仅在低置信度时触发。

### 增量摄取去重

上传文档通过 IngestionPipeline 的 UPSERTS 策略处理：内容不变的重复上传被跳过，内容变化的重传会原地更新，不会无限堆积重复 chunk。docstore 按 index_id 持久化到磁盘，进程重启后去重记忆不丢失。

## 可观测性

系统集成了 OpenInference + OpenTelemetry 可观测性（通过环境变量门控），可导出 LLM 调用链到 OTLP 收集器。详见 `docs/observability.md`。

## 评测

检索质量评测脚本位于 `evals/` 目录：

```bash
# 检索评测
python evals/run_retrieval_eval.py

# 混合检索评测
python evals/run_hybrid_eval.py

# Rerank 评测
python evals/run_rerank_eval.py

# Workflow 检索评测
python evals/run_workflow_retrieval_eval.py
```

评测结果保存在 `evals/results/`，详见 `evals/README.md`。

## 部署

### 使用启动脚本

```bash
# Linux/macOS
./backend.bash

# Windows
backend.bat
```

### Docker 部署

```bash
# 构建并运行（需自行编写 Dockerfile）
docker build -t cuitcca .
docker run -p 8522:8522 -v $(pwd)/data:/app/data cuitcca
```

### 环境变量

生产环境务必配置 `CUITCCA_API_KEY` 和 `COOKIE_SECURE=True`，并通过 `CORS_ORIGINS` 限制允许的源。

## 贡献

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献流程。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。
