# mj-agent Makefile
# 跨平台便捷命令：
#   make help          查看所有命令
#   make venv          创建/重建 venv
#   make install       安装开发依赖
#   make test          跑测试
#   make run-gateway   启动 FastAPI 网关
#   make run-worker    启动 worker
#   make lint / format 代码检查 / 格式化
#   make clean         清理缓存
#
# Windows 用户如果没装 make，可以直接用 .\scripts\setup.ps1 与 python 命令。

VENV       := .venv
VENV_BIN   := $(VENV)/bin
ifeq ($(OS),Windows_NT)
	VENV_BIN := $(VENV)/Scripts
endif
PY         := $(VENV_BIN)/python
PIP        := $(VENV_BIN)/pip
PYTEST     := $(VENV_BIN)/pytest
UVICORN    := $(VENV_BIN)/uvicorn

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "mj-agent Makefile"
	@echo ""
	@echo "  make venv         创建 .venv"
	@echo "  make install      安装开发依赖（生产+测试+lint）"
	@echo "  make install-base 仅安装生产依赖"
	@echo "  make test         跑测试（pytest）"
	@echo "  make cov          跑测试 + 覆盖率报告"
	@echo "  make run-gateway  启动 FastAPI 网关（端口 8080）"
	@echo "  make run-worker   启动 Agent Worker"
	@echo "  make lint         ruff + mypy"
	@echo "  make format       black + ruff --fix"
	@echo "  make clean        清理 __pycache__ / .pytest_cache / .coverage"
	@echo "  make clean-venv   删除 .venv（慎重）"

.PHONY: venv
venv:
	@if [ ! -d "$(VENV)" ]; then \
		echo "==> 创建 $(VENV)"; \
		python -m venv $(VENV); \
	else \
		echo "==> $(VENV) 已存在"; \
	fi

.PHONY: install
install: venv
	$(PIP) install --upgrade pip wheel setuptools
	$(PIP) install -r requirements-dev.txt
	@echo "✅ 开发依赖已安装"

.PHONY: install-base
install-base: venv
	$(PIP) install --upgrade pip wheel setuptools
	$(PIP) install -r requirements.txt
	@echo "✅ 生产依赖已安装"

.PHONY: test
test:
	$(PYTEST) -v

.PHONY: cov
cov:
	$(PYTEST) --cov=app --cov=config --cov-report=term-missing --cov-report=html

.PHONY: run-gateway
run-gateway:
	$(UVICORN) app.gateway.router:build_app --factory --host 0.0.0.0 --port 8080 --reload

.PHONY: run-worker
run-worker:
	$(PY) -m app.worker.runner

.PHONY: lint
lint:
	$(VENV_BIN)/ruff check app config tests
	$(VENV_BIN)/mypy app config

.PHONY: format
format:
	$(VENV_BIN)/black app config tests
	$(VENV_BIN)/ruff check --fix app config tests

.PHONY: clean
clean:
	find . -type d -name "__pycache__" -not -path "./$(VENV)/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -not -path "./$(VENV)/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -not -path "./$(VENV)/*" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage
	rm -rf htmlcov
	@echo "✅ 缓存已清理"

.PHONY: clean-venv
clean-venv:
	rm -rf $(VENV)
	@echo "✅ .venv 已删除"
