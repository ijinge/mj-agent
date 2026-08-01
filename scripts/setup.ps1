# scripts/setup.ps1 — Windows PowerShell 一键环境搭建
# 用法：
#   .\scripts\setup.ps1            # 创建 .venv 并装 dev 依赖
#   .\scripts\setup.ps1 -Base      # 只装生产依赖（不装 ruff/black/pytest）
#   .\scripts\setup.ps1 -Recreate  # 删除现有 .venv 后重建
[CmdletBinding()]
param(
    [switch]$Base,
    [switch]$Recreate,
    [switch]$NoTest
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

Write-Host "==> mj-agent setup" -ForegroundColor Cyan
Write-Host "    project: $projectRoot"

# 1. 选择 Python
$python = $null
foreach ($c in @("python", "python3", "py")) {
    $found = Get-Command $c -ErrorAction SilentlyContinue
    if ($found) { $python = $found.Path; break }
}
if (-not $python) {
    Write-Error "未找到 python，请先安装 Python 3.11+ 并加入 PATH"
    exit 1
}
Write-Host "    python: $python ($(& $python --version 2>&1))"

# 2. 重建 venv
$venvPath = Join-Path $projectRoot ".venv"
if ($Recreate -and (Test-Path $venvPath)) {
    Write-Host "==> 删除旧 venv" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvPath
}
if (-not (Test-Path $venvPath)) {
    Write-Host "==> 创建 .venv" -ForegroundColor Cyan
    & $python -m venv $venvPath
} else {
    Write-Host "==> .venv 已存在，跳过创建" -ForegroundColor Green
}

# 3. 升级 pip
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"
Write-Host "==> 升级 pip" -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip wheel setuptools 2>&1 | Out-Host

# 4. 安装依赖
if ($Base) {
    $reqFile = "requirements.txt"
} else {
    $reqFile = "requirements-dev.txt"
}
Write-Host "==> 安装依赖 ($reqFile)" -ForegroundColor Cyan
& $venvPip install -r $reqFile 2>&1 | Out-Host

# 5. 验证安装
Write-Host "==> 验证安装" -ForegroundColor Cyan
& $venvPython -c "import sys; print('  python:', sys.version.split()[0])"
& $venvPython -c "import fastapi, pydantic, redis; print('  fastapi:', fastapi.__version__)" 2>&1 | Out-Host
& $venvPython -c "import langgraph, langchain_core; print('  langgraph:', langgraph.__file__)" 2>&1 | Out-Host
& $venvPython -c "import mcp; print('  mcp:', getattr(mcp, '__version__', 'installed'))" 2>&1 | Out-Host

# 6. 跑测试
if (-not $NoTest -and -not $Base) {
    Write-Host "==> 运行测试" -ForegroundColor Cyan
    & $venvPython -m pytest 2>&1 | Out-Host
}

Write-Host ""
Write-Host "✅ 环境已就绪" -ForegroundColor Green
Write-Host "   激活 venv:   .\.venv\Scripts\Activate.ps1"
Write-Host "   跑 gateway:  .\.venv\Scripts\uvicorn.exe app.gateway.router:app --reload"
Write-Host "   跑 worker:   .\.venv\Scripts\python.exe -m app.worker.runner"
