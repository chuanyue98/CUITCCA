.PHONY: install dev test lint typecheck security clean run format help frontend-install frontend-dev frontend-build

install: ## 安装依赖
	python -m pip install -e ".[dev]" || python -m pip install -e . && pip install -r dev-requirements.txt

dev: ## 启动开发服务器（热重载）
	cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8522

run: ## 启动生产服务器
	cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8522

test: ## 运行测试
	python -m pytest tests/ -v

lint: ## 代码风格检查
	ruff check backend/ tests/

typecheck: ## 类型检查
	mypy backend/app/ tests/ --ignore-missing-imports

security: ## 安全扫描
	pip-audit
	bandit -r backend/app/ -ll

format: ## 自动格式化
	ruff check --fix backend/ tests/
	ruff format backend/ tests/

clean: ## 清理缓存
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +

frontend-install: ## 安装前端依赖
	cd frontend && npm install

frontend-dev: ## 启动前端开发服务器
	cd frontend && npm run dev

frontend-build: ## 构建前端生产产物
	cd frontend && npm run build

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
