param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OpenClawRoot = "",
    [string]$PluginSource = ""
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path $RepoRoot
if (-not $OpenClawRoot) {
    $OpenClawRoot = Join-Path $repo "openclaw\node_modules\openclaw"
}
if (-not $PluginSource) {
    $PluginSource = Join-Path $repo "openclaw\node_modules\@openclaw\codex"
}
$openclaw = Resolve-Path $OpenClawRoot
$destination = Join-Path $openclaw "dist\extensions\codex"
$sourceAvailable = Test-Path $PluginSource
if ($sourceAvailable) {
    $source = Resolve-Path $PluginSource
    $package = Get-Content (Join-Path $source "package.json") -Raw | ConvertFrom-Json
    if ($package.name -ne "@openclaw/codex" -or $package.version -ne "2026.7.1-1") {
        throw "Unexpected Codex migration provider identity/version."
    }
    if (-not (Test-Path (Join-Path $source "dist\index.js"))) {
        throw "Codex migration provider dist/index.js is missing."
    }

    if (Test-Path $destination) {
        $resolvedDestination = Resolve-Path $destination
        if (-not $resolvedDestination.Path.StartsWith($openclaw.Path)) {
            throw "Refusing to replace migration provider outside OpenClaw runtime."
        }
        Remove-Item -LiteralPath $resolvedDestination.Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Copy-Item -LiteralPath (Join-Path $source "dist") -Destination $destination -Recurse
    Copy-Item -LiteralPath (Join-Path $source "package.json") -Destination $destination
    Copy-Item -LiteralPath (Join-Path $source "openclaw.plugin.json") -Destination $destination
    New-Item -ItemType Directory -Force -Path (Join-Path $destination "node_modules") | Out-Null
    foreach ($dependency in @("typebox", "ws", "zod")) {
        $dependencySource = Join-Path $source "node_modules\$dependency"
        if (-not (Test-Path $dependencySource)) {
            throw "Codex migration dependency is missing: $dependency"
        }
        Copy-Item -LiteralPath $dependencySource `
            -Destination (Join-Path $destination "node_modules") -Recurse
    }

    $metadata = [ordered]@{
        schema_version = 1
        package = "@openclaw/codex"
        version = "2026.7.1-1"
        purpose = "oauth_migration_only"
        codex_agent_runtime_dependencies_bundled = $false
        omitted_dependencies = @("@openai/codex", "@openai/codex-*-*")
    }
    $metadata | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $destination "migration-bundle.json") -Encoding utf8
} elseif (-not (Test-Path (Join-Path $destination "migration-bundle.json"))) {
    throw "Neither the pinned source package nor a staged migration provider exists."
}

$runtimeNodeModules = Resolve-Path (Join-Path $repo "openclaw\node_modules")
$runtimePackages = @(
    (Join-Path $runtimeNodeModules "@openclaw\codex"),
    (Join-Path $runtimeNodeModules "@openai\codex")
)
$openaiScope = Join-Path $runtimeNodeModules "@openai"
if (Test-Path $openaiScope) {
    $runtimePackages += @(
        Get-ChildItem -LiteralPath $openaiScope -Directory |
            Where-Object { $_.Name -eq "codex" -or $_.Name -like "codex-*" } |
            Select-Object -ExpandProperty FullName
    )
}
foreach ($runtimePackage in $runtimePackages) {
    if (-not (Test-Path $runtimePackage)) {
        continue
    }
    $resolvedPackage = Resolve-Path $runtimePackage
    if (-not $resolvedPackage.Path.StartsWith($runtimeNodeModules.Path)) {
        throw "Refusing to prune Codex runtime outside repo-local node_modules."
    }
    Remove-Item -LiteralPath $resolvedPackage.Path -Recurse -Force
}

$codexBinaries = @(
    Get-ChildItem -LiteralPath $runtimeNodeModules -Recurse -File -Filter "codex.exe"
)
if ($codexBinaries.Count -gt 0) {
    throw "Codex agent runtime binaries remain after OAuth provider staging."
}

$size = Get-ChildItem -LiteralPath $destination -Recurse -File |
    Measure-Object Length -Sum
if ($size.Sum -gt 32MB) {
    throw "Codex OAuth migration bundle unexpectedly exceeds 32 MB."
}
Write-Host "[OK] Staged trusted OAuth-only Codex migration provider: $([Math]::Round($size.Sum / 1MB, 2)) MB"
Write-Host "[OK] Pruned full Codex agent runtime packages and platform binaries."
