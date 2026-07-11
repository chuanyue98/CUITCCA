# 贡献指南

> 基于 FastAPI + LlamaIndex 的校园智能问答系统，支持文档上传、知识库管理与 RAG 问答。

欢迎为 CUITCCA（校园 AI 助手）项目贡献代码！本文档将帮助你快速搭建开发环境并了解项目的代码规范与提交流程。

## 环境要求

- **Python** >= 3.12
- **Node.js**（可选，用于前端本地开发与调试）
- [uv](https://github.com/astral-sh/uv) 包管理器（推荐）或标准 `pip`

## 开发环境搭建

### 1. 克隆仓库

```bash
git clone https://github.com/ChuanYuei/CUITCCA.git
cd CUITCCA
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
```

### 3. 激活虚拟环境

Linux / macOS：

```bash
source .venv/bin/activate
```

Windows (PowerShell)：

```powershell
.venv\Scripts\Activate.ps1
```

Windows (CMD)：

```cmd
.venv\Scripts\activate.bat
```

### 4. 安装依赖

推荐方式（若 `pyproject.toml` 中已声明 dev 依赖组）：

```bash
pip install -e ".[dev]"
```

备选方式（手动安装开发依赖）：

```bash
pip install -e .
pip install pytest pytest-cov pytest-asyncio ruff mypy pip-audit bandit
```

### 5. 配置环境变量

将 `.env.example` 复制为 `.env` 并填写相关配置：

```bash
cp backend/.env.example backend/.env
```

随后编辑 `backend/.env`，填入 `OPENAI_API_KEY` 等必要配置项。

### 6. 运行测试

使用 Makefile：

```bash
make test
```

或直接使用 pytest：

```bash
python -m pytest tests/ -v
```

## 代码规范

项目使用 [ruff](https://github.com/astral-sh/ruff) 进行代码风格检查，使用 [mypy](https://github.com/python/mypy) 进行静态类型检查。

- 代码风格检查：`make lint`
- 类型检查：`make typecheck`
- 自动格式化：`make format`

### 强制要求

- 所有代码必须通过 `ruff check` 和 `mypy` 才能合并。
- **行宽限制**：120 字符。
- **Python 版本**：3.12+（请勿使用低于 3.12 的语法特性或标准库 API）。

## 提交规范

- 使用清晰、语义化的 commit message，简要说明本次改动的目的与内容。
- 一个 Pull Request 只做一件事，避免在一个 PR 中混合多个不相关的改动。
- 提交 PR 前请确保所有测试通过：

  ```bash
  make test
  ```

- 建议在提交前运行完整检查：

  ```bash
  make lint typecheck test
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
├── frontend/            # 前端页面 (HTML/CSS/JS)
├── tests/               # 测试用例
├── data/                # 数据存储 (向量库、索引、上传文件)
├── docs/                # 项目文档
├── .github/             # CI/CD 工作流
├── Makefile             # 常用命令快捷入口
├── pyproject.toml       # 项目配置与依赖声明
└── README.md
```

## 反馈渠道

- **GitHub Issues**：请在 [Issues](https://github.com/ChuanYuei/CUITCCA/issues) 中提交 Bug 报告、功能建议或使用问题。
- **邮箱**：如有其他疑问或合作意向，请通过邮箱联系项目维护者。

感谢你的贡献！
