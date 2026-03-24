# 机器人巡检监控系统 - 一键启动脚本
# 使用方式：在 PowerShell 中运行 .\start.ps1，或双击 start.bat

$ROOT = $PSScriptRoot
$CONDA_PYTHON = "$ROOT\.conda\python.exe"
$BACKEND_DIR = "$ROOT\backend"

# ── 颜色输出工具 ─────────────────────────────────────────────
function Info($msg)    { Write-Host "  [INFO] $msg" -ForegroundColor Cyan }
function Success($msg) { Write-Host "  [ OK ] $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Err($msg)     { Write-Host "  [ERR ] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor Blue
Write-Host "   机器人巡检监控系统 - 一键启动" -ForegroundColor Blue
Write-Host "  ==========================================" -ForegroundColor Blue
Write-Host ""

# ── 检查 Python 环境 ──────────────────────────────────────────
if (Test-Path $CONDA_PYTHON) {
    Success "找到本地 conda 环境：.conda\python.exe"
    $PYTHON = $CONDA_PYTHON
} else {
    Warn "未找到本地 .conda 环境，尝试使用系统 Python..."
    $PYTHON = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if (-not $PYTHON) {
        Err "未找到 Python，请先安装 conda 环境或确认 Python 在 PATH 中。"
        exit 1
    }
    Info "使用系统 Python：$PYTHON"
}

# ── 检查 uvicorn ──────────────────────────────────────────────
$UVICORN = Split-Path $PYTHON | Join-Path -ChildPath "uvicorn.exe"
if (-not (Test-Path $UVICORN)) {
    Info "正在安装依赖（pip install -r requirements.txt）..."
    & $PYTHON -m pip install -r "$BACKEND_DIR\requirements.txt" -q
    if ($LASTEXITCODE -ne 0) {
        Err "依赖安装失败，请检查网络或手动运行 pip install。"
        exit 1
    }
    Success "依赖安装完成。"
}

# ── 启动后端服务 ──────────────────────────────────────────────
Info "正在启动后端服务..."
Info "地址：http://localhost:8000"
Write-Host ""
Write-Host "  按 Ctrl+C 停止服务" -ForegroundColor DarkGray
Write-Host ""

Set-Location $BACKEND_DIR
& $PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
