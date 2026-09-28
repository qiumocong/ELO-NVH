param(
    [string]$Version = "0.1.1"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv-release\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Release Python environment not found: $python. Create .venv-release first."
}

$buildWindows = Join-Path $repoRoot "build_windows.ps1"
& $buildWindows -PythonPath $python
if ($LASTEXITCODE -ne 0) {
    throw "build_windows.ps1 failed with exit code $LASTEXITCODE"
}

$buildInstaller = Join-Path $repoRoot "build_installer.ps1"
& $buildInstaller -Version $Version -PythonPath $python -SkipAppBuild
if ($LASTEXITCODE -ne 0) {
    throw "build_installer.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "Light build completed: dist\installer\ELO-NVH-Setup-$Version.exe"
