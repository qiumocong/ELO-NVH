param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$versionFile = Join-Path $repoRoot ".app_version"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$explicitVersion = -not [string]::IsNullOrWhiteSpace($Version)
if (-not $explicitVersion) {
    $Version = [System.IO.File]::ReadAllText($versionFile).Trim()
}

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Version must use MAJOR.MINOR.PATCH format, for example 0.1.5."
}

if ($explicitVersion) {
    [System.IO.File]::WriteAllText($versionFile, $Version + [Environment]::NewLine, $utf8NoBom)
}

function Update-VersionLine {
    param(
        [string]$Path,
        [string]$Pattern,
        [string]$Description
    )

    $content = [System.IO.File]::ReadAllText($Path)
    if ($content -notmatch $Pattern) {
        throw "Could not find the version declaration in $Description ($Path)."
    }
    # Use ${1}/${2}; without braces .NET interprets a version beginning with
    # a digit as part of the capture-group number (for example $10.1.1).
    $replacement = '${1}' + $Version + '${2}'
    $updated = [regex]::Replace($content, $Pattern, $replacement, 1)
    if ($updated -ne $content) {
        [System.IO.File]::WriteAllText($Path, $updated, $utf8NoBom)
    }
}

Update-VersionLine `
    (Join-Path $repoRoot "pyproject.toml") `
    '(?m)^(version\s*=\s*")[^"]+(".*)$' `
    "pyproject.toml"

Write-Host "Application version synchronized to $Version."
Write-Output $Version
