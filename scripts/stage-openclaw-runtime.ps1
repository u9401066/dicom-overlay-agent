param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "build\openclaw-runtime"),
    [int]$MaxRuntimeMB = 500,
    [int]$MinFreeDiskMB = 2048
)

$ErrorActionPreference = "Stop"

$repo = Resolve-Path $RepoRoot
$repoPath = [System.IO.Path]::GetFullPath($repo.Path).TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
if (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
    # A caller-supplied relative output is always repo-relative, independent of
    # the shell's current directory.
    $OutputRoot = Join-Path $repoPath $OutputRoot
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot).TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
$repoChildPrefix = $repoPath + [System.IO.Path]::DirectorySeparatorChar
$outputIsRepoRoot = $OutputRoot.Equals(
    $repoPath,
    [System.StringComparison]::OrdinalIgnoreCase
)
$outputIsRepoChild = $OutputRoot.StartsWith(
    $repoChildPrefix,
    [System.StringComparison]::OrdinalIgnoreCase
)
if ($outputIsRepoRoot -or -not $outputIsRepoChild) {
    throw "OpenClaw staging output must be a true child of the repo root: $OutputRoot"
}
$drive = Get-PSDrive -Name $repo.Drive.Name
if ($drive.Free -lt ($MinFreeDiskMB * 1MB)) {
    throw "Insufficient free disk for OpenClaw staging: $([Math]::Round($drive.Free / 1MB, 2)) MB"
}
$source = Join-Path $repo "openclaw\node_modules\openclaw"
if (-not (Test-Path (Join-Path $source "openclaw.mjs"))) {
    throw "OpenClaw runtime not found. Run scripts\install-openclaw-local.bat first."
}

# OpenClaw 2026.7.1-2 still loads these files when it initializes a fresh
# agent workspace.  The npm package publishes HEARTBEAT.md in the primary
# template directory and the other canonical templates under docs/reference.
# Validate the pinned upstream assets before copying anything: a partially
# installed package must fail the build instead of depending on stale runtime
# state from openclaw-home.
$runtimeTemplateFiles = [ordered]@{
    "src\agents\templates\HEARTBEAT.md" = "HEARTBEAT.md"
    "docs\reference\templates\AGENTS.md" = "AGENTS.md"
    "docs\reference\templates\SOUL.md" = "SOUL.md"
    "docs\reference\templates\TOOLS.md" = "TOOLS.md"
    "docs\reference\templates\IDENTITY.md" = "IDENTITY.md"
    "docs\reference\templates\USER.md" = "USER.md"
    "docs\reference\templates\BOOTSTRAP.md" = "BOOTSTRAP.md"
}
foreach ($relative in $runtimeTemplateFiles.Keys) {
    $template = Join-Path $source $relative
    if (-not (Test-Path -LiteralPath $template -PathType Leaf)) {
        throw "Pinned OpenClaw runtime is missing required workspace template $($runtimeTemplateFiles[$relative]): $template"
    }
    if ((Get-Item -LiteralPath $template).Length -le 0) {
        throw "Pinned OpenClaw workspace template is empty: $template"
    }
}
& (Join-Path $PSScriptRoot "stage-codex-auth-migration-provider.ps1") `
    -RepoRoot $repo.Path `
    -OpenClawRoot $source

$outputParent = Split-Path $OutputRoot -Parent
if (-not (Test-Path $outputParent)) {
    New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
}

if (Test-Path $OutputRoot) {
    $resolved = Resolve-Path -LiteralPath $OutputRoot
    $candidate = Get-Item -LiteralPath $resolved.Path -Force
    while (-not $candidate.FullName.Equals(
        $repoPath,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        if (($candidate.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to recursively remove staging output through a reparse point: $($candidate.FullName)"
        }
        $candidate = $candidate.Parent
        if ($null -eq $candidate) {
            throw "Refusing to remove unresolved staging output: $resolved"
        }
    }
    Remove-Item -LiteralPath $resolved.Path -Recurse -Force
}

$dest = Join-Path $OutputRoot "openclaw\node_modules\openclaw"
New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null

Write-Host "[INFO] Staging slim OpenClaw runtime..."
Copy-Item -LiteralPath $source -Destination $dest -Recurse

$packageOnlyDirs = @("docs", "src", "patches", "scripts")
foreach ($name in $packageOnlyDirs) {
    $path = Join-Path $dest $name
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

# Restore only the seven upstream template assets used by
# ensureAgentWorkspace().  They are copied byte-for-byte from the pinned npm
# package and keep their published relative paths; no repo-owned fallback or
# generated template may silently mask an incomplete OpenClaw install.
$stagedTemplatePaths = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
foreach ($relative in $runtimeTemplateFiles.Keys) {
    $sourceTemplate = Join-Path $source $relative
    $stagedTemplate = Join-Path $dest $relative
    $stagedTemplateParent = Split-Path $stagedTemplate -Parent
    New-Item -ItemType Directory -Force -Path $stagedTemplateParent | Out-Null
    Copy-Item -LiteralPath $sourceTemplate -Destination $stagedTemplate -Force
    [void]$stagedTemplatePaths.Add([System.IO.Path]::GetFullPath($stagedTemplate))
}

$packageOnlyFiles = @("CHANGELOG.md", "README.md", "pnpm-workspace.yaml")
foreach ($name in $packageOnlyFiles) {
    Remove-Item -LiteralPath (Join-Path $dest $name) -Force -ErrorAction SilentlyContinue
}

# npm packages occasionally publish local development environment files. They
# are not required at runtime and portable builds must never carry .env data.
Get-ChildItem -LiteralPath $dest -Recurse -Force -File |
    Where-Object {
        $_.Name -ieq ".env" -or
        $_.Name.StartsWith(".env.", [System.StringComparison]::OrdinalIgnoreCase)
    } |
    Remove-Item -Force

$nonRuntimeExtensions = @(
    ".ts", ".mts", ".cts", ".map", ".md", ".txt", ".scss", ".coffee",
    ".ps1", ".sh", ".yml", ".yaml", ".bcmap", ".pfb", ".eslintrc",
    ".nycrc", ".proto", ".rs"
)
$bundledSkills = Join-Path $dest "skills"
Get-ChildItem -Recurse -File $dest |
    Where-Object {
        $underPreservedMarkdownRoot = $_.FullName.StartsWith(
            "$bundledSkills\",
            [System.StringComparison]::OrdinalIgnoreCase
        )
        if (-not $underPreservedMarkdownRoot) {
            $underPreservedMarkdownRoot = $stagedTemplatePaths.Contains(
                [System.IO.Path]::GetFullPath($_.FullName)
            )
        }
        ($nonRuntimeExtensions -contains $_.Extension) -and
        (-not $underPreservedMarkdownRoot)
    } |
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
$nativePruneDirs += Get-ChildItem $nodeModules -Directory -Filter "sqlite-vec-*" |
    Where-Object { $_.Name -ne "sqlite-vec-windows-x64" }
$piTuiNative = Join-Path $nodeModules "@earendil-works\pi-tui\native"
if (Test-Path $piTuiNative) {
    # pi-tui publishes native helpers below a single package instead of using
    # platform-specific package names.  Keep only the Windows x64 prebuild.
    $nativePruneDirs += Get-ChildItem $piTuiNative -Directory |
        Where-Object { $_.Name -ne "win32" }
    $piTuiWindowsPrebuilds = Join-Path $piTuiNative "win32\prebuilds"
    if (Test-Path $piTuiWindowsPrebuilds) {
        $nativePruneDirs += Get-ChildItem $piTuiWindowsPrebuilds -Directory |
            Where-Object { $_.Name -ne "win32-x64" }
    }
}
$treeSitterPrebuilds = Join-Path $nodeModules "tree-sitter-bash\prebuilds"
if (Test-Path $treeSitterPrebuilds) {
    $nativePruneDirs += Get-ChildItem $treeSitterPrebuilds -Directory |
        Where-Object { $_.Name -ne "win32-x64" }
}
foreach ($dir in $nativePruneDirs) {
    Remove-Item -LiteralPath $dir.FullName -Recurse -Force
}

# node-pty PDBs are linker/debug symbols, not executable runtime payloads.
# The retained Windows x64 binaries load without them.
Get-ChildItem -LiteralPath $nodeModules -Recurse -File -Filter "*.pdb" |
    Remove-Item -Force

# tree-sitter-bash ships a precompiled win32-x64 .node binary.  Its generated
# C parser and headers are build inputs only; keep JSON queries/metadata and
# the prebuilt runtime artifact.
$treeSitterSource = Join-Path $nodeModules "tree-sitter-bash\src"
if (Test-Path -LiteralPath $treeSitterSource) {
    Get-ChildItem -LiteralPath $treeSitterSource -Recurse -File |
        Where-Object { $_.Extension -in @(".c", ".h") } |
        Remove-Item -Force
}

# Keep OpenClaw's internal dist chunks intact. The agent harness resolves
# bundled plugin public surfaces at runtime; pruning dist/extensions,
# dist/plugins, or dist/plugin-sdk can pass ``gateway --help`` yet fail only
# when the first image-analysis agent run starts.

$sum = Get-ChildItem -Recurse -File $OutputRoot | Measure-Object Length -Sum
$mb = [Math]::Round($sum.Sum / 1MB, 2)
if ($sum.Sum -gt ($MaxRuntimeMB * 1MB)) {
    throw "Staged OpenClaw runtime exceeds $MaxRuntimeMB MB budget: $mb MB"
}
Write-Host "[OK] Staged slim OpenClaw runtime: $($sum.Count) files, $mb MB"
