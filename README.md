# 校园AI助手 (CUIT Campus AI Assistant)

基于 FastAPI + LlamaIndex 的校园智能问答系统，支持文档上传、知识库管理、RAG 问答。

## 快速开始

### 前置要求
- Python >= 3.12
- [uv](https://github.com/astral-sh/uv) 包管理器

### 安装与运行

```bash
git clone https://github.com/ChuanYuei/CUITCCA.git
cd CUITCCA
uv sync

# 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入 OPENAI_API_KEY 等配置

# 启动后端
cd backend
uv run python app/main.py
```

## 项目结构

```
CUITCCA/
├── backend/              # FastAPI 后端
│   └── app/
│       ├── main.py                  # 应用入口
│       ├── router/                  # API 路由
│       ├── handlers/                # 业务逻辑处理
│       ├── models/                  # Pydantic 数据模型
│       ├── dependencies/            # 依赖注入
│       ├── exceptions/              # 异常处理
│       ├── utils/                   # 工具函数
│       └── configs/                 # 配置 (LLM, 环境变量)
├── frontend/             # 前端页面 (HTML/CSS/JS)
├── tests/                # 测试文件 (pytest)
├── data/                 # 数据存储 (索引, 上传文件)
├── docs/                 # 开发文档
├── .github/              # CI/CD 与 Dependabot 配置
├── backend.bash          # Linux/macOS 启动脚本
├── backend.bat           # Windows 启动脚本
├── pyproject.toml        # 项目依赖与工具配置
├── uv.lock               # uv 锁定的依赖版本
└── .python-version       # Python 版本声明
```

## 主要功能

- **RAG 问答**: 基于文档索引的智能问答，检索层默认启用 BM25(jieba分词)+向量 RRF 混合检索与条件触发式 cross-encoder rerank，评测数据见 `evals/README.md`
- **增量摄取去重**: 上传文档按内容 sha256 去重（UPSERTS），内容不变的重复上传直接跳过、内容变化原地更新，不会无限堆积重复 chunk
- **多轮流式对话**: 聊天页基于 `/graph/chat_stream` 实现真实 token 级流式输出（非模拟打字机），支持连续追问、上下文记忆
- **Markdown 渲染 + 引用来源**: 回答内容使用 marked.js + DOMPurify 渲染并净化，命中知识库时在回复下方展示可展开的参考来源片段
- **对话历史持久化**: 对话记录保存在浏览器 `localStorage`，刷新页面自动恢复；点击清空对话会同时重置服务端会话上下文
- **暗色模式**: 跟随系统 `prefers-color-scheme` 自动切换，覆盖聊天、知识库管理、反馈、指南全部页面
- **知识库管理**: 创建/删除索引，上传文档，增删节点
- **文件上传**: 支持 PDF、DOCX、TXT、MD、CSV、XLSX
- **QA 生成**: 从文档自动生成问答对
- **图查询**: 多引擎知识图谱查询

## API 概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/web/` | GET | 前端页面 |
| `/index/` | GET/POST | 索引管理 (创建/查询/删除) |
| `/graph/` | GET/POST | 图查询/流式聊天 |
| `/response/` | POST | 响应查询 |
| `/manage/` | POST | 管理接口 (环境变量/api key) |
| `/test/` | POST | 测试工具 |

## 运行测试

```bash
uv run pytest tests/ -v --cov=backend/app
```

## 技术栈

- **后端**: Python 3.12, FastAPI, LlamaIndex
- **AI**: OpenAI API / 兼容接口, HuggingFace Embeddings
- **前端**: HTML, CSS, JavaScript (无框架/无构建步骤), marked.js + DOMPurify (Markdown 渲染与净化，本地 vendored)
- **测试**: pytest