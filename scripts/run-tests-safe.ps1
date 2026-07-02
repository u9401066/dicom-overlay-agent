$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache-codex"
}
New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR | Out-Null
if (-not $env:UV_NO_PROGRESS) {
    $env:UV_NO_PROGRESS = "1"
}
if (-not $env:UV_PYTHON_DOWNLOADS) {
    $env:UV_PYTHON_DOWNLOADS = "never"
}

$tmpRoot = Join-Path $repoRoot "data\tmp\pytest-safe"
New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null
$env:TMP = $tmpRoot
$env:TEMP = $tmpRoot

$pytestArgs = @(
    "run",
    "python",
    "-m",
    "pytest",
    "-p",
    "no:cacheprovider",
    "--basetemp",
    (Join-Path $tmpRoot "basetemp"),
    "tests/unit",
    "tests/smoke"
)

if ($args.Count -gt 0) {
    $pytestArgs += $args
}

& uv @pytestArgs
exit $LASTEXITCODE
