param(
    [string]$PythonPath = "",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

if ($Version) {
    $versionScript = Join-Path $repoRoot "packaging\set_app_version.ps1"
    & $versionScript -Version $Version
    if (-not $?) {
        throw "Could not synchronize application version."
    }
}

$python = if ($PythonPath) { (Resolve-Path -LiteralPath $PythonPath).Path } else { Join-Path $repoRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Missing Python. Please create .venv or add Python to PATH."
    }
    $python = $pythonCommand.Source
}

# PyInstaller recreates this directory during COLLECT. Model files copied from
# logs\models may carry the ReadOnly attribute, which prevents Windows cleanup.
$distApp = Join-Path $repoRoot "dist\ELO-NVH"
if (Test-Path -LiteralPath $distApp) {
    $distItems = @((Get-Item -LiteralPath $distApp -Force)) + @(Get-ChildItem -LiteralPath $distApp -Force -Recurse)
    foreach ($item in $distItems) {
        if (($item.Attributes -band [System.IO.FileAttributes]::ReadOnly) -ne 0) {
            $item.Attributes = $item.Attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly)
        }
    }
}

& $python -m PyInstaller --clean --noconfirm packaging/yanpu.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller Build Failed, Exit Code $LASTEXITCODE."
}
$modelSource = Join-Path $repoRoot "logs\models"
$modelTarget = Join-Path $repoRoot "dist\ELO-NVH\logs\models"
if (-not (Test-Path -LiteralPath $modelSource)) {
    throw "Do not find model directory: $modelSource"
}
New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
Copy-Item -Path (Join-Path $modelSource "*.pth") -Destination $modelTarget -Force
# Keep the build output writable even when the source model is marked ReadOnly.
Get-ChildItem -LiteralPath $modelTarget -Filter "*.pth" -File -Force | ForEach-Object {
    if (($_.Attributes -band [System.IO.FileAttributes]::ReadOnly) -ne 0) {
        $_.Attributes = $_.Attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly)
    }
}
Write-Host "Build completed: dist\ELO-NVH\ELO-NVH.exe"
