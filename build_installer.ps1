param(
    [string]$Version = "0.1.0",
    [switch]$SkipAppBuild
)

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

if (-not $SkipAppBuild) {
    Write-Host "正在构建 PyInstaller 发布目录..."
    & $python -m PyInstaller --clean --noconfirm packaging\yanpu.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码 $LASTEXITCODE。"
    }
}

$modelSource = Join-Path $repoRoot "logs\models"
$modelTarget = Join-Path $repoRoot "dist\ELO-NVH\logs\models"
if (-not (Test-Path -LiteralPath $modelSource)) {
    throw "未找到模型目录: $modelSource"
}
New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
Copy-Item -Path (Join-Path $modelSource "*.pth") -Destination $modelTarget -Force

$appExe = Join-Path $repoRoot "dist\ELO-NVH\ELO-NVH.exe"
if (-not (Test-Path -LiteralPath $appExe)) {
    throw "未找到 $appExe。请先完成应用程序构建。"
}

$isccCandidates = @(
    (Join-Path ${env:LOCALAPPDATA} "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "未找到 Inno Setup 的 ISCC.exe。请安装 Inno Setup 6 后重试。"
}

Write-Host "正在生成安装程序..."
& $iscc "/DMyAppVersion=$Version" (Join-Path $repoRoot "packaging\yanpu.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup 构建失败，退出码 $LASTEXITCODE。"
}

$installer = Join-Path $repoRoot "dist\installer\ELO-NVH-Setup-$Version.exe"
if (Test-Path -LiteralPath $installer) {
    $sizeGB = [math]::Round((Get-Item -LiteralPath $installer).Length / 1GB, 2)
    Write-Host "安装程序已生成: $installer ($sizeGB GB)"
} else {
    throw "Inno Setup 未生成预期文件: $installer"
}
