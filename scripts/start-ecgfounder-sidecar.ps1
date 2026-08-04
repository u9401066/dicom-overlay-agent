[CmdletBinding()]
param(
    [string]$RuntimeDir = "data\external\ecgfounder-runtime",
    [string]$Registry = "data\eval-datasets\meeti-1000-all\waveform-registry.json",
    [int]$Port = 18790,
    [string]$SelfTestArtifact = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ResolvedRuntime = if ([IO.Path]::IsPathRooted($RuntimeDir)) {
    [IO.Path]::GetFullPath($RuntimeDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $RepoRoot $RuntimeDir))
}
$ResolvedRegistry = if ([IO.Path]::IsPathRooted($Registry)) {
    [IO.Path]::GetFullPath($Registry)
} else {
    [IO.Path]::GetFullPath((Join-Path $RepoRoot $Registry))
}
$PythonExe = Join-Path $ResolvedRuntime ".venv\Scripts\python.exe"
$Checkpoint = Join-Path $ResolvedRuntime "checkpoints\12_lead_ECGFounder.pth"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "ECGFounder runtime is missing. Run scripts\setup-ecgfounder-sidecar.ps1 first."
}
if (-not (Test-Path -LiteralPath $ResolvedRegistry -PathType Leaf)) {
    throw "Waveform registry is missing: $ResolvedRegistry"
}
if (-not (Test-Path -LiteralPath $Checkpoint -PathType Leaf)) {
    throw "ECGFounder checkpoint is missing: $Checkpoint"
}
if ([string]::IsNullOrWhiteSpace($env:DICOM_ECGFOUNDER_TOKEN) -or $env:DICOM_ECGFOUNDER_TOKEN.Length -lt 32) {
    throw "Set DICOM_ECGFOUNDER_TOKEN to a random value of at least 32 characters."
}

$Arguments = @(
    "-m", "sidecars.ecgfounder.server",
    "--registry", $ResolvedRegistry,
    "--checkpoint", $Checkpoint,
    "--port", $Port.ToString()
)
if (-not [string]::IsNullOrWhiteSpace($SelfTestArtifact)) {
    $Arguments += @("--self-test-artifact", $SelfTestArtifact)
}

Push-Location $RepoRoot
try {
    & $PythonExe @Arguments
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
