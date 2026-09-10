param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$NodeExecutable = ""
)

$ErrorActionPreference = "Stop"
function Get-PreparationFileHash([string]$Path) {
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace("-", "").ToLowerInvariant()
    } finally {
        $hasher.Dispose()
    }
}

$repo = (Resolve-Path -LiteralPath $RepoRoot).Path
$entry = Join-Path $repo "openclaw\node_modules\openclaw\openclaw.mjs"
$installedPath = Join-Path $repo "openclaw\node_modules\openclaw\package.json"
$desired = Get-Content -LiteralPath (Join-Path $repo "openclaw\package.json") -Raw | ConvertFrom-Json
$installed = Get-Content -LiteralPath $installedPath -Raw | ConvertFrom-Json
if ($installed.name -ne "openclaw" -or $installed.version -ne $desired.dependencies.openclaw) {
    throw "Installed OpenClaw identity/version does not match the pinned package."
}
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    throw "Pinned OpenClaw public CLI entry is missing."
}
if (-not $NodeExecutable) {
    $portable = Join-Path $repo "node\node.exe"
    if (Test-Path -LiteralPath $portable -PathType Leaf) {
        $NodeExecutable = $portable
    } else {
        $NodeExecutable = @(Get-Command node -CommandType Application -ErrorAction Stop)[0].Source
    }
}
$NodeExecutable = (Resolve-Path -LiteralPath $NodeExecutable).Path
$preparationState = Join-Path $repo ("data\tmp\openclaw-package-prepare-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $preparationState -Force | Out-Null

# Use the public CLI before relocation/pruning. A package installed with
# --ignore-scripts can defer its own lifecycle work until this first invocation.
# Run it with a clean credential-free environment and isolated state/CWD. Never
# copy authentication or change the user's HOME/Codex/OpenClaw environment.
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $NodeExecutable
$startInfo.Arguments = "`"$entry`" gateway --help"
$startInfo.WorkingDirectory = $preparationState
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.EnvironmentVariables.Clear()
foreach ($name in @("SystemRoot", "WINDIR", "SystemDrive", "TEMP", "TMP", "PATH", "PATHEXT", "COMSPEC")) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ($null -ne $value) { $startInfo.EnvironmentVariables[$name] = $value }
}
$startInfo.EnvironmentVariables["OPENCLAW_HOME"] = $preparationState
$startInfo.EnvironmentVariables["OPENCLAW_STATE_DIR"] = $preparationState
$startInfo.EnvironmentVariables["OPENCLAW_CONFIG_PATH"] = Join-Path $preparationState "openclaw.json"
$startInfo.EnvironmentVariables["CI"] = "1"
$process = New-Object System.Diagnostics.Process
$process.StartInfo = $startInfo
try {
    if (-not $process.Start()) { throw "Could not start pinned OpenClaw package preparation." }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(60000)) {
        # Only the helper process tree we just created, never an existing Gateway.
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        throw "Pinned OpenClaw public CLI preparation timed out; no runtime was staged."
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $stdout | Set-Content -LiteralPath (Join-Path $preparationState "stdout.log") -Encoding utf8
    $stderr | Set-Content -LiteralPath (Join-Path $preparationState "stderr.log") -Encoding utf8
    $validHelp = $stdout.Contains("Run the WebSocket Gateway")
    [ordered]@{
        schema_version = 1
        package_version = $installed.version
        public_command = "gateway --help"
        isolated_state = $true
        inherited_credentials = $false
        exit_code = $process.ExitCode
        expected_help_observed = $validHelp
        stdout_sha256 = Get-PreparationFileHash (Join-Path $preparationState "stdout.log")
        stderr_sha256 = Get-PreparationFileHash (Join-Path $preparationState "stderr.log")
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $preparationState "receipt.json") -Encoding utf8
    if ($process.ExitCode -ne 0 -or -not $validHelp) {
        throw "Pinned OpenClaw public CLI preparation failed; reinstall the locked package with lifecycle scripts enabled. Diagnostics: $preparationState"
    }
    Write-Host "[OK] Prepared pinned OpenClaw package through isolated public gateway --help."
} finally {
    $process.Dispose()
}
