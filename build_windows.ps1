$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "未找到 Python。请先创建 .venv，或将 Python 加入 PATH。"
    }
    $python = $pythonCommand.Source
}

& $python -m PyInstaller --clean --noconfirm packaging/yanpu.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 构建失败，退出码 $LASTEXITCODE。"
}
Write-Host "构建完成: dist\ELO-NVH\ELO-NVH.exe"
