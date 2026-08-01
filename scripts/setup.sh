#!/usr/bin/env bash
# scripts/setup.sh — macOS/Linux 一键环境搭建
# 用法：
#   ./scripts/setup.sh            # 创建 .venv 并装 dev 依赖
#   ./scripts/setup.sh --base     # 只装生产依赖
#   ./scripts/setup.sh --recreate # 删旧 venv 后重建
#   ./scripts/setup.sh --no-test  # 跳过 pytest
set -euo pipefail

BASE_ONLY=0
RECREATE=0
NO_TEST=0
for arg in "$@"; do
    case "$arg" in
        --base) BASE_ONLY=1 ;;
        --recreate) RECREATE=1 ;;
        --no-test) NO_TEST=1 ;;
        *) echo "unknown arg: $arg"; exit 1 ;;
    esac
done

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "\033[36m==> mj-agent setup\033[0m"
echo "    project: $PROJECT_ROOT"

# 1. Python
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "未找到 $PYTHON，请先安装 Python 3.11+"
    exit 1
fi
echo "    python: $($PYTHON --version 2>&1)"

# 2. venv
VENV_PATH="$PROJECT_ROOT/.venv"
if [ "$RECREATE" = "1" ] && [ -d "$VENV_PATH" ]; then
    echo -e "\033[33m==> 删除旧 venv\033[0m"
    rm -rf "$VENV_PATH"
fi
if [ ! -d "$VENV_PATH" ]; then
    echo -e "\033[36m==> 创建 .venv\033[0m"
    "$PYTHON" -m venv "$VENV_PATH"
else
    echo -e "\033[32m==> .venv 已存在，跳过创建\033[0m"
fi

VENV_PY="$VENV_PATH/bin/python"
VENV_PIP="$VENV_PATH/bin/pip"

# 3. 升级 pip
echo -e "\033[36m==> 升级 pip\033[0m"
"$VENV_PY" -m pip install --upgrade pip wheel setuptools >/dev/null

# 4. 安装依赖
if [ "$BASE_ONLY" = "1" ]; then
    REQ_FILE="requirements.txt"
else
    REQ_FILE="requirements-dev.txt"
fi
echo -e "\033[36m==> 安装依赖 ($REQ_FILE)\033[0m"
"$VENV_PIP" install -r "$REQ_FILE"

# 5. 验证
echo -e "\033[36m==> 验证安装\033[0m"
"$VENV_PY" -c "import sys; print('  python:', sys.version.split()[0])"
"$VENV_PY" -c "import fastapi, pydantic, redis; print('  fastapi:', fastapi.__version__)"
"$VENV_PY" -c "import langgraph, langchain_core; print('  langgraph: ok')"
"$VENV_PY" -c "import mcp; print('  mcp: ok')"

# 6. 测试
if [ "$NO_TEST" = "0" ] && [ "$BASE_ONLY" = "0" ]; then
    echo -e "\033[36m==> 运行测试\033[0m"
    "$VENV_PY" -m pytest
fi

echo ""
echo -e "\033[32m✅ 环境已就绪\033[0m"
echo "   激活 venv:   source .venv/bin/activate"
echo "   跑 gateway:  .venv/bin/uvicorn app.gateway.router:app --reload"
echo "   跑 worker:   .venv/bin/python -m app.worker.runner"
