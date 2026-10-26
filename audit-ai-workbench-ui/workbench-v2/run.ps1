$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot 'venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) {
    throw '未找到项目虚拟环境。请先运行 setup.ps1。'
}

Set-Location -LiteralPath $ProjectRoot
& $Python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
