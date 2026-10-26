$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot 'venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) {
    throw '未找到项目虚拟环境。请先运行 setup.ps1。'
}

# 0.0.0.0 便于同一局域网内手机浏览器访问；仅本机可改为 127.0.0.1
$HostBind = if ($env:WORKBENCH_HOST) { $env:WORKBENCH_HOST } else { '0.0.0.0' }
$Port = if ($env:WORKBENCH_PORT) { $env:WORKBENCH_PORT } else { '8765' }

Set-Location -LiteralPath $ProjectRoot
Write-Host "工作台启动于 http://${HostBind}:${Port}/ （手机请用电脑局域网 IP 访问）"
& $Python -m uvicorn backend.main:app --host $HostBind --port $Port
