<#
.SYNOPSIS
    Download a portable Node.js runtime (node.exe only) into node\ for the
    DICOM Overlay Agent "zero-install" portable bundle (Core 4).

.DESCRIPTION
    OpenClaw's Gateway runs on Node.js. To ship a USB-portable bundle that needs
    no system Node.js, this script downloads the official Windows x64 Node.js zip
    and extracts only node.exe into <repo>\node\node.exe. gateway_manager.py
    prefers this bundled binary over PATH.

.PARAMETER Version
    Node.js version to fetch (default: 24.18.0 LTS).
#>
param(
    [string]$Version = "24.18.0",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$repo = Resolve-Path $RepoRoot
$nodeDir = Join-Path $repo "node"
$nodeExe = Join-Path $nodeDir "node.exe"

if (Test-Path $nodeExe) {
    $existing = (& $nodeExe --version) 2>$null
    if ($existing -eq "v$Version") {
        Write-Host "[OK] Portable Node.js is current: $nodeExe ($existing)"
        exit 0
    }
    Write-Host "[INFO] Updating portable Node.js: $existing -> v$Version"
}

$arch = "x64"
$zipName = "node-v$Version-win-$arch.zip"
$url = "https://nodejs.org/dist/v$Version/$zipName"
$tmp = Join-Path $env:TEMP "doa-node-$Version"
$zipPath = Join-Path $env:TEMP $zipName

Write-Host "[INFO] Downloading $url ..."
Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing

Write-Host "[INFO] Extracting node.exe ..."
if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
Expand-Archive -LiteralPath $zipPath -DestinationPath $tmp -Force

$srcExe = Join-Path $tmp "node-v$Version-win-$arch\node.exe"
if (-not (Test-Path $srcExe)) {
    throw "node.exe not found in archive: $srcExe"
}

New-Item -ItemType Directory -Force -Path $nodeDir | Out-Null
Copy-Item -LiteralPath $srcExe -Destination $nodeExe -Force

Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue

$mb = [Math]::Round((Get-Item $nodeExe).Length / 1MB, 2)
$ver = (& $nodeExe --version) 2>$null
Write-Host "[OK] Bundled portable Node.js ready: $nodeExe ($ver, $mb MB)"
