param(
    [string]$ModelId = "openai/gpt-5.4-mini",
    [string]$ManifestPath = "",
    [string]$ProviderProfile = "",
    [string]$CodexHome = "",
    [string]$CodexCommand = "",
    [int]$TimeoutSec = 300,
    [int]$Limit = 0,
    [string]$ExperimentDir = "",
    [ValidateSet("clinical", "minimal_control")]
    [string]$AnalysisPromptProfile = "clinical",
    [ValidateSet("off", "minimal", "low", "medium", "high")]
    [string]$ThinkingLevel = "medium",
    [switch]$MultiPass,
    [int]$MultiPassMaxTargets = 3,
    [int]$MultiPassMaxEkgSystematicProbes = 2,
    [switch]$EcgFounderWaveformEvidence,
    [switch]$NoManageEcgFounderSidecar,
    [switch]$RequirePerfect,
    [double]$MinStrictPassRate = 0.75,
    [double]$MinMeanPartialCredit = 0.85,
    [switch]$Resume,
    [switch]$ResumeRetryErrors,
    [ValidateSet("reject", "mark")]
    [string]$ResumeLegacyPolicy = "reject",
    [switch]$SkipArtifactVerify
)

$ErrorActionPreference = "Stop"

# The Python runner is canonical. This file only adapts PowerShell arguments so
# lifecycle, ownership, protocol, and artifact gates cannot drift by shell.
$canonicalRepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $canonicalRepoRoot
$canonicalArgs = @(
    "run", "python", "scripts/run-meeti-openclaw-experiment.py",
    "--model-id", $ModelId,
    "--timeout-sec", $TimeoutSec,
    "--limit", $Limit,
    "--analysis-prompt-profile", $AnalysisPromptProfile,
    "--thinking-level", $ThinkingLevel,
    "--multi-pass-max-targets", $MultiPassMaxTargets,
    "--multi-pass-max-ekg-systematic-probes", $MultiPassMaxEkgSystematicProbes,
    "--min-strict-pass-rate", $MinStrictPassRate,
    "--min-mean-partial-credit", $MinMeanPartialCredit,
    "--resume-legacy-policy", $ResumeLegacyPolicy
)
if ($ManifestPath) { $canonicalArgs += @("--manifest", $ManifestPath) }
if ($ProviderProfile) { $canonicalArgs += @("--provider-profile", $ProviderProfile) }
if ($CodexHome) { $canonicalArgs += @("--codex-home", $CodexHome) }
if ($CodexCommand) { $canonicalArgs += @("--codex-command", $CodexCommand) }
if ($ExperimentDir) { $canonicalArgs += @("--experiment-dir", $ExperimentDir) }
if ($MultiPass) { $canonicalArgs += "--multi-pass" }
if ($EcgFounderWaveformEvidence) {
    $canonicalArgs += "--ecgfounder-waveform-evidence"
}
if ($NoManageEcgFounderSidecar) {
    $canonicalArgs += "--no-manage-ecgfounder-sidecar"
}
if ($RequirePerfect) { $canonicalArgs += "--require-perfect" }
if ($Resume) { $canonicalArgs += "--resume" }
if ($ResumeRetryErrors) { $canonicalArgs += "--resume-retry-errors" }
if ($SkipArtifactVerify) { $canonicalArgs += "--skip-artifact-verify" }

& uv @canonicalArgs
exit $LASTEXITCODE
