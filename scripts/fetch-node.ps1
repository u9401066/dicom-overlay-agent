<#
.SYNOPSIS
    Download a portable Node.js runtime and its LICENSE into node\ for the
    DICOM Overlay Agent "zero-install" portable bundle (Core 4).

.DESCRIPTION
    OpenClaw's Gateway runs on Node.js. To ship a USB-portable bundle that needs
    no system Node.js, this script downloads the official Windows x64 Node.js zip
    verifies the official SHA-256 and extracts only node.exe and LICENSE.
    gateway_manager.py
    prefers this bundled binary over PATH.

.PARAMETER Version
    Node.js version to fetch (default: 24.18.0 LTS).
#>
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version = "24.18.0",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

$repo = Resolve-Path $RepoRoot
$nodeDir = Join-Path $repo "node"
$nodeExe = Join-Path $nodeDir "node.exe"
$nodeLicense = Join-Path $nodeDir "LICENSE"
foreach ($target in @($nodeDir, $nodeExe, $nodeLicense)) {
    if ((Test-Path -LiteralPath $target) -and
        ((Get-Item -LiteralPath $target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing to replace portable Node through a reparse point: $target"
    }
}

if (Test-Path $nodeExe) {
    $existing = (& $nodeExe --version) 2>$null
    if ($existing -eq "v$Version" -and (Test-Path -LiteralPath $nodeLicense) -and
        (Get-Item -LiteralPath $nodeLicense).Length -gt 0) {
        Write-Host "[OK] Portable Node.js is current: $nodeExe ($existing)"
        exit 0
    }
    Write-Host "[INFO] Updating portable Node.js: $existing -> v$Version"
}

$arch = "x64"
$zipName = "node-v$Version-win-$arch.zip"
$url = "https://nodejs.org/dist/v$Version/$zipName"
$zipPath = Join-Path ([IO.Path]::GetTempPath()) ("doa-node-" + [Guid]::NewGuid().ToString('N') + '.zip')

Write-Host "[INFO] Downloading $url ..."
try {
    Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
    $checksums = (Invoke-WebRequest -Uri "https://nodejs.org/dist/v$Version/SHASUMS256.txt" -UseBasicParsing).Content
    $checksumPattern = '(?m)^([a-fA-F0-9]{64})\s+' + [regex]::Escape($zipName) + '\s*$'
    if ($checksums -notmatch $checksumPattern) { throw "Official Node checksum entry missing." }
    $expectedChecksum = $Matches[1]
    $hasher = [Security.Cryptography.SHA256]::Create()
    $zipStream = [IO.File]::OpenRead($zipPath)
    try { $actualChecksum = [BitConverter]::ToString($hasher.ComputeHash($zipStream)).Replace('-', '') }
    finally { $zipStream.Dispose(); $hasher.Dispose() }
    if ($actualChecksum -ine $expectedChecksum) {
        throw "Portable Node archive SHA-256 mismatch."
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        New-Item -ItemType Directory -Force -Path $nodeDir | Out-Null
        foreach ($name in @('node.exe', 'LICENSE')) {
            $entry = $archive.GetEntry("node-v$Version-win-$arch/$name")
            if ($null -eq $entry -or $entry.Length -le 0) { throw "Required Node archive entry missing: $name" }
        }
        foreach ($name in @('node.exe', 'LICENSE')) {
            $entry = $archive.GetEntry("node-v$Version-win-$arch/$name")
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $nodeDir $name), $true)
        }
    } finally { $archive.Dispose() }
} finally {
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
}

$mb = [Math]::Round((Get-Item $nodeExe).Length / 1MB, 2)
$ver = (& $nodeExe --version) 2>$null
Write-Host "[OK] Bundled portable Node.js ready: $nodeExe ($ver, $mb MB)"
