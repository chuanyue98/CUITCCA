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
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 等配置

# 启动后端
cd backend
uv run python app/main.py
```

## 项目结构

```
CUITCCA/
├── backend/          # FastAPI 后端
│   └── app/
│       ├── main.py              # 应用入口
│       ├── router/              # API 路由
│       ├── handlers/            # 业务逻辑处理
│       ├── models/              # Pydantic 数据模型
│       ├── dependencies/        # 依赖注入
│       ├── exceptions/          # 异常处理
│       ├── utils/               # 工具函数
│       └── configs/             # 配置 (LLM, 环境变量)
├── frontend/         # 前端页面 (HTML/CSS/JS)
├── tests/            # 测试文件 (unittest)
├── data/             # 数据存储 (索引, 上传文件)
├── docs/             # 开发文档
└── pyproject.toml    # 项目依赖配置
```

## 主要功能

- **RAG 问答**: 基于文档索引的智能问答
- **知识库管理**: 创建/删除索引，上传文档，增删节点
- **文件上传**: 支持 PDF、DOCX、TXT、MD、CSV、XLSX
- **QA 生成**: 从文档自动生成问答对
- **图查询**: 多引擎知识图谱查询
- **流式响应**: SSE 流式聊天

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
python -m unittest discover -s tests -v
```

## 技术栈

- **后端**: Python 3.12, FastAPI, LlamaIndex, LangChain
- **AI**: OpenAI API / 兼容接口, HuggingFace Embeddings
- **前端**: HTML, CSS, JavaScript (无框架)
- **测试**: unittest