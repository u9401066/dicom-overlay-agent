param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "build\openclaw-runtime")
)

$ErrorActionPreference = "Stop"

$repo = Resolve-Path $RepoRoot
$source = Join-Path $repo "openclaw\node_modules\openclaw"
if (-not (Test-Path (Join-Path $source "openclaw.mjs"))) {
    throw "OpenClaw runtime not found. Run scripts\install-openclaw-local.bat first."
}

$outputParent = Split-Path $OutputRoot -Parent
if (-not (Test-Path $outputParent)) {
    New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
}

if (Test-Path $OutputRoot) {
    $resolved = Resolve-Path $OutputRoot
    if (-not $resolved.Path.StartsWith($repo.Path)) {
        throw "Refusing to remove output outside repo: $resolved"
    }
    Remove-Item -LiteralPath $resolved.Path -Recurse -Force
}

$dest = Join-Path $OutputRoot "openclaw\node_modules\openclaw"
New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null

Write-Host "[INFO] Staging slim OpenClaw runtime..."
Copy-Item -LiteralPath $source -Destination $dest -Recurse

$packageOnlyDirs = @("docs", "src", "patches", "scripts", "skills")
foreach ($name in $packageOnlyDirs) {
    $path = Join-Path $dest $name
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

$packageOnlyFiles = @("CHANGELOG.md", "README.md", "pnpm-workspace.yaml")
foreach ($name in $packageOnlyFiles) {
    Remove-Item -LiteralPath (Join-Path $dest $name) -Force -ErrorAction SilentlyContinue
}

$nonRuntimeExtensions = @(
    ".ts", ".mts", ".cts", ".map", ".md", ".txt", ".scss", ".coffee",
    ".ps1", ".sh", ".yml", ".yaml", ".bcmap", ".pfb", ".eslintrc",
    ".nycrc", ".proto", ".rs"
)
Get-ChildItem -Recurse -File $dest |
    Where-Object { $nonRuntimeExtensions -contains $_.Extension } |
    Remove-Item -Force

# DICOM Overlay Agent runs on Windows x64. Remove platform-native payloads for
# other OS/CPU targets; these dominate the npm package size and slow PyInstaller.
$nodeModules = Join-Path $dest "node_modules"
$nativePruneDirs = @()
if (Test-Path (Join-Path $nodeModules "@napi-rs")) {
    $nativePruneDirs += Get-ChildItem (Join-Path $nodeModules "@napi-rs") -Directory |
        Where-Object { $_.Name -like "canvas-*" -and $_.Name -ne "canvas-win32-x64-msvc" }
}
if (Test-Path (Join-Path $nodeModules "@lydell")) {
    $nativePruneDirs += Get-ChildItem (Join-Path $nodeModules "@lydell") -Directory |
        Where-Object { $_.Name -like "node-pty-*" -and $_.Name -ne "node-pty-win32-x64" }
}
if (Test-Path (Join-Path $nodeModules "@mariozechner")) {
    $nativePruneDirs += Get-ChildItem (Join-Path $nodeModules "@mariozechner") -Directory |
        Where-Object { $_.Name -like "clipboard-*" -and $_.Name -ne "clipboard-win32-x64-msvc" }
}
$treeSitterPrebuilds = Join-Path $nodeModules "tree-sitter-bash\prebuilds"
if (Test-Path $treeSitterPrebuilds) {
    $nativePruneDirs += Get-ChildItem $treeSitterPrebuilds -Directory |
        Where-Object { $_.Name -ne "win32-x64" }
}
foreach ($dir in $nativePruneDirs) {
    Remove-Item -LiteralPath $dir.FullName -Recurse -Force
}

# The desktop app only uses the Gateway + model/provider surface. Bundled UI,
# browser, voice, phone, and file-transfer plugins are disabled at runtime.
$disabledBundledDirs = @(
    "dist\extensions",
    "dist\canvas-host",
    "dist\plugins",
    "dist\plugin-sdk"
)
foreach ($rel in $disabledBundledDirs) {
    $path = Join-Path $dest $rel
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

$largeDisabledDeps = @(
    "@napi-rs",
    "@lydell",
    "@mariozechner",
    "pdfjs-dist",
    "playwright-core",
    "tree-sitter-bash",
    "web-tree-sitter",
    "typescript",
    "quickjs-wasi"
)
foreach ($rel in $largeDisabledDeps) {
    $path = Join-Path $nodeModules $rel
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

$sum = Get-ChildItem -Recurse -File $OutputRoot | Measure-Object Length -Sum
$mb = [Math]::Round($sum.Sum / 1MB, 2)
Write-Host "[OK] Staged slim OpenClaw runtime: $($sum.Count) files, $mb MB"
