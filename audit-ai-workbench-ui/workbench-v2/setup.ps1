$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot 'venv\Scripts\python.exe'
$BundledPython = 'C:\Users\11575\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

function Resolve-Python {
    foreach ($candidate in @($BundledPython, 'py', 'python')) {
        if ($candidate -eq 'py' -or $candidate -eq 'python') {
            $command = Get-Command $candidate -ErrorAction SilentlyContinue
            if ($command) { return $command.Source }
            continue
        }
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    throw '未找到可用的 Python。请先安装 Python 3.11+，并确保 python 或 py 在 PATH 中。'
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    $systemPython = Resolve-Python
    & $systemPython -m venv (Join-Path $ProjectRoot 'venv')
}

& $VenvPython -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
Write-Host '安装完成。运行 .\run.ps1 启动工作台。'
