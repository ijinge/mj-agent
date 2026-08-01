# scripts/activate.sh — source 当前 shell 激活 venv（Linux/macOS）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC1091
source "$PROJECT_ROOT/.venv/bin/activate"
echo "venv activated: $VIRTUAL_ENV"
