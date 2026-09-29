param(
    [string]$Version = "0.1.3",
    [switch]$SkipAppBuild,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$python = if ($PythonPath) { (Resolve-Path -LiteralPath $PythonPath).Path } else { Join-Path $repoRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Do not find Python. Please create .venv or add Python to PATH."
    }
    $python = $pythonCommand.Source
}

if (-not $SkipAppBuild) {
    Write-Host "Building PyInstaller Release..."
    $buildWindows = Join-Path $repoRoot "build_windows.ps1"
    & $buildWindows -PythonPath $python -Version $Version
    if ($LASTEXITCODE -ne 0) {
        throw "Application build failed, Exit Code $LASTEXITCODE."
    }
} else {
    $versionText = [System.IO.File]::ReadAllText((Join-Path $repoRoot "app\version.py"))
    if ($versionText -notmatch ('APP_VERSION\s*=\s*"' + [regex]::Escape($Version) + '"')) {
        throw "The existing application does not contain APP_VERSION=$Version. Rebuild it with -Version $Version before using -SkipAppBuild."
    }
    $projectText = [System.IO.File]::ReadAllText((Join-Path $repoRoot "pyproject.toml"))
    if ($projectText -notmatch ('(?m)^version\s*=\s*"' + [regex]::Escape($Version) + '"')) {
        throw "pyproject.toml does not contain version=$Version. Rebuild it with -Version $Version before using -SkipAppBuild."
    }
}

$modelSource = Join-Path $repoRoot "logs\models"
$modelTarget = Join-Path $repoRoot "dist\ELO-NVH\logs\models"
if (-not (Test-Path -LiteralPath $modelSource)) {
    throw "Do not find model directory: $modelSource"
}
New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
Copy-Item -Path (Join-Path $modelSource "*.pth") -Destination $modelTarget -Force

$appExe = Join-Path $repoRoot "dist\ELO-NVH\ELO-NVH.exe"
if (-not (Test-Path -LiteralPath $appExe)) {
    throw "Do not find $appExe. Please complete the application build first."
}

$isccCandidates = @(
    (Join-Path ${env:LOCALAPPDATA} "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Do not find Inno Setup's ISCC.exe. Please install Inno Setup 6 and try again."
}

Write-Host "Building installer..."
& $iscc "/DMyAppVersion=$Version" (Join-Path $repoRoot "packaging\yanpu.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup Build Failed, Exit Code $LASTEXITCODE."
}

$installer = Join-Path $repoRoot "dist\installer\ELO-NVH-Setup-$Version.exe"
if (Test-Path -LiteralPath $installer) {
    $sizeMB = [math]::Round((Get-Item -LiteralPath $installer).Length / 1MB, 2)
    Write-Host "Installer has been generated: $installer ($sizeMB MB; if .bin volume files are generated, please publish them together with the main program)"
} else {
    throw "Inno Setup did not generate the expected file: $installer"
}
