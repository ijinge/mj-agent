# scripts/activate.ps1 — 当前 PowerShell 激活 venv（Windows）
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$activate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Error "未找到 $activate，请先运行 .\scripts\setup.ps1"
    exit 1
}
. $activate
Write-Host "venv activated: $env:VIRTUAL_ENV" -ForegroundColor Green
