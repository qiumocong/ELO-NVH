param(
    [string]$Version = "0.1.1"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv-release\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到 CPU 发布环境 $python。请先按 README 的轻量发布版步骤创建 .venv-release。"
}

& (Join-Path $repoRoot "build_windows.ps1") -PythonPath $python
if ($LASTEXITCODE -ne 0) {
    throw "轻量版 exe 构建失败，退出码 $LASTEXITCODE。"
}

& (Join-Path $repoRoot "build_installer.ps1") -Version $Version -PythonPath $python -SkipAppBuild
if ($LASTEXITCODE -ne 0) {
    throw "轻量版安装包构建失败，退出码 $LASTEXITCODE。"
}

Write-Host "轻量版发布完成: dist\installer\ELO-NVH-Setup-$Version.exe"
