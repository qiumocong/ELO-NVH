param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv-release\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {throw "Release Python environment not found: $python. Create .venv-release first."}

$buildInstaller = Join-Path $repoRoot "build_installer.ps1"
& $buildInstaller -Version $Version -PythonPath $python
if ($LASTEXITCODE -ne 0) {throw "build_installer.ps1 failed with exit code $LASTEXITCODE"}

$Version = [System.IO.File]::ReadAllText((Join-Path $repoRoot ".app_version")).Trim()
Write-Host "Light build completed: dist\installer\ELO-NVH-Setup-$Version.exe"
