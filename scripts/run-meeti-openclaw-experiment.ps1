param(
    [string]$ModelId = "openai/gpt-5.6-luna",
    [string]$ManifestPath = "",
    [string]$ProviderProfile = "",
    [int]$TimeoutSec = 90,
    [int]$Limit = 0,
    [string]$ExperimentDir = "",
    [switch]$MultiPass,
    [int]$MultiPassMaxTargets = 3,
    [int]$MultiPassMaxEkgSystematicProbes = 2,
    [switch]$RequirePerfect
)

$ErrorActionPreference = "Stop"

function Write-ExperimentJson {
    param(
        [string]$Path,
        [hashtable]$Payload
    )
    $Payload | ConvertTo-Json -Depth 20 | Set-Content -Path $Path -Encoding UTF8
}

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return @{
        Output = @($output)
        ExitCode = $exitCode
    }
}

function Invoke-EvalWithGatewayRetry {
    param(
        [string[]]$EvalArgs,
        [int]$MaxAttempts = 6,
        [int]$DelaySeconds = 5
    )
    $attempt = 1
    $combinedOutput = @()
    while ($attempt -le $MaxAttempts) {
        $combinedOutput += "=== eval attempt $attempt ==="
        $result = Invoke-NativeCommand -FilePath "uv" -Arguments $EvalArgs
        $combinedOutput += $result.Output
        $outputText = $result.Output | Out-String
        if ($result.ExitCode -eq 0) {
            return @{
                Output = $combinedOutput
                ExitCode = 0
                Attempts = $attempt
            }
        }
        if ($outputText -notmatch "gateway starting; retry shortly" -or $attempt -ge $MaxAttempts) {
            return @{
                Output = $combinedOutput
                ExitCode = $result.ExitCode
                Attempts = $attempt
            }
        }
        $combinedOutput += "Gateway not ready; retrying after $DelaySeconds seconds."
        Start-Sleep -Seconds $DelaySeconds
        $attempt += 1
    }
}

function Load-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return
    }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line -split "=", 2
        $name = $parts[0].Trim()
        $value = $parts[1]
        if ($name) {
            Set-Item -Path ("Env:" + $name) -Value $value
        }
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

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
$uvTmp = Join-Path $repoRoot "data\tmp\uv"
New-Item -ItemType Directory -Force -Path $uvTmp | Out-Null
$env:TMP = $uvTmp
$env:TEMP = $uvTmp

Load-DotEnv (Join-Path $repoRoot ".env")

$env:OPENCLAW_HOME = Join-Path $repoRoot "openclaw-home"
$env:OPENCLAW_STATE_DIR = $env:OPENCLAW_HOME
$env:HOME = $env:OPENCLAW_HOME
$env:USERPROFILE = $env:OPENCLAW_HOME

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$safeModel = $ModelId -replace "[^A-Za-z0-9._-]", "_"
$experimentDir = if ($ExperimentDir) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ExperimentDir)
} else {
    Join-Path $repoRoot "data\experiments\meeti-$stamp-$safeModel"
}
New-Item -ItemType Directory -Force -Path $experimentDir | Out-Null

$experimentJson = Join-Path $experimentDir "experiment.json"
$modelsListPath = Join-Path $experimentDir "openclaw-models-list.txt"
$configBuilderPath = Join-Path $experimentDir "build-openclaw-config.py"
$configGenerationPath = Join-Path $experimentDir "openclaw-config-generation.json"
$gatewayOut = Join-Path $experimentDir "gateway.stdout.log"
$gatewayErr = Join-Path $experimentDir "gateway.stderr.log"
$evalOut = Join-Path $experimentDir "eval-console.log"
$evalDir = Join-Path $experimentDir "eval"
$scorecardPath = Join-Path $evalDir "scorecard.json"
$scorecardRebuilt = Join-Path $evalDir "scorecard.rebuilt.json"
$reviewDir = Join-Path $evalDir "review"
$configPath = Join-Path $experimentDir "openclaw.experiment.json"

$openclawCli = Join-Path $repoRoot "openclaw\node_modules\openclaw\openclaw.mjs"
$baseConfigPath = Join-Path $repoRoot "openclaw\openclaw.json"
$manifestPath = if ($ManifestPath) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ManifestPath)
} else {
    Join-Path $repoRoot "data\eval-datasets\meeti-1000-all\manifest.json"
}

$effectiveProviderProfile = $ProviderProfile
if (-not $effectiveProviderProfile -and $env:DICOM_OVERLAY_PROVIDER_PROFILE) {
    $effectiveProviderProfile = $env:DICOM_OVERLAY_PROVIDER_PROFILE
}
if (-not $effectiveProviderProfile -and $ModelId -eq "openai/gpt-5.4-mini") {
    $effectiveProviderProfile = "openai-vision"
}
if (-not $effectiveProviderProfile -and $ModelId -eq "openai/gpt-5.6-luna") {
    $effectiveProviderProfile = "openai-luna"
}
if (-not $effectiveProviderProfile -and $ModelId.ToLowerInvariant().StartsWith("openrouter/")) {
    $effectiveProviderProfile = "openrouter"
}
$env:DICOM_OVERLAY_PROVIDER_PROFILE = $effectiveProviderProfile

$configBuilder = @'
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from dicom_overlay.infrastructure.openclaw_settings import (
    build_openclaw_config,
    default_provider_profiles,
    merge_openclaw_config,
)


def read_json(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


base_config = Path(sys.argv[1])
target_config = Path(sys.argv[2])
model_id = sys.argv[3]
profile_key = sys.argv[4]

existing = read_json(base_config)
metadata = {
    "provider_profile": profile_key,
    "requested_model": model_id,
}

if profile_key:
    profiles = default_provider_profiles()
    profile = next(
        (
            item
            for item in profiles
            if item.key == profile_key or item.provider_id == profile_key
        ),
        None,
    )
    if profile is None:
        known = sorted({item.key for item in profiles} | {item.provider_id for item in profiles})
        raise SystemExit(f"Unknown provider profile '{profile_key}'. Known profiles: {', '.join(known)}")

    model = model_id
    provider_prefix = f"{profile.provider_id}/"
    if model.lower().startswith(provider_prefix.lower()):
        model = model[len(provider_prefix):]
    profile = replace(profile, model=model)
    managed = build_openclaw_config(profile)
    merged = merge_openclaw_config(existing, managed)
    metadata.update(
        {
            "provider_profile": profile.key,
            "provider_id": profile.provider_id,
            "model_ref": profile.model_ref,
            "api_key_env": profile.api_key_env,
        }
    )
else:
    merged = existing
    defaults = merged.setdefault("agents", {}).setdefault("defaults", {})
    defaults.setdefault("model", {})["primary"] = model_id
    defaults["model"].setdefault("fallbacks", [])
    models = defaults.setdefault("models", {})
    models.setdefault(model_id, {"alias": model_id})
    metadata.update(
        {
            "provider_profile": "",
            "provider_id": "",
            "model_ref": model_id,
            "api_key_env": "",
        }
    )

write_json(target_config, merged)
print(json.dumps(metadata, indent=2, ensure_ascii=False))
'@

$configBuilder | Set-Content -Path $configBuilderPath -Encoding UTF8
$configGenerationResult = Invoke-NativeCommand `
    -FilePath "uv" `
    -Arguments @("run", "python", $configBuilderPath, $baseConfigPath, $configPath, $ModelId, $effectiveProviderProfile)
$configGenerationOutput = $configGenerationResult.Output
$configGenerationExitCode = $configGenerationResult.ExitCode
if ($configGenerationExitCode -ne 0) {
    @($configGenerationOutput) | Set-Content -Path $configGenerationPath -Encoding UTF8
    Write-ExperimentJson $experimentJson @{
        status = "blocked"
        reason = "could not generate experiment OpenClaw config"
        requested_model = $ModelId
        provider_profile = $effectiveProviderProfile
        config_builder = $configBuilderPath
        config_generation_log = $configGenerationPath
        manifest = $manifestPath
        created_at = (Get-Date).ToString("o")
    }
    Write-Host "BLOCKED: could not generate experiment OpenClaw config"
    Write-Host "Experiment record: $experimentJson"
    exit 20
}
@($configGenerationOutput) | Set-Content -Path $configGenerationPath -Encoding UTF8
$env:OPENCLAW_CONFIG_PATH = $configPath

$modelListResult = Invoke-NativeCommand `
    -FilePath "node" `
    -Arguments @($openclawCli, "models", "list")
$modelListRaw = $modelListResult.Output
$modelListExitCode = $modelListResult.ExitCode
$modelListOutput = $modelListRaw | Out-String
$modelListOutput | Set-Content -Path $modelsListPath -Encoding UTF8
$modelCatalogWarning = ""
$modelCatalogInput = @()
foreach ($line in ($modelListOutput -split "`r?`n")) {
    $columns = @($line.Trim() -split "\s+")
    if ($columns.Count -ge 2 -and $columns[0] -eq $ModelId) {
        $modelCatalogInput = @($columns[1] -split "\+")
        break
    }
}

if ($modelCatalogInput.Count -eq 0) {
    Write-ExperimentJson $experimentJson @{
        status = "blocked"
        reason = "requested model id is not exposed by the effective OpenClaw catalog"
        requested_model = $ModelId
        provider_profile = $effectiveProviderProfile
        openclaw_config = $configPath
        config_builder = $configBuilderPath
        config_generation_log = $configGenerationPath
        model_catalog_log = $modelsListPath
        model_catalog_exit_code = $modelListExitCode
        manifest = $manifestPath
        created_at = (Get-Date).ToString("o")
    }
    Write-Host "BLOCKED: requested model is not in the effective OpenClaw catalog: $ModelId"
    Write-Host "Experiment record: $experimentJson"
    exit 20
}
if ($modelListExitCode -ne 0) {
    $modelCatalogWarning = "OpenClaw models list exited non-zero after emitting a usable model capability row; the run will continue and retain the log."
}

if ($modelCatalogInput -notcontains "image") {
    Write-ExperimentJson $experimentJson @{
        status = "blocked"
        reason = "requested model does not advertise image input"
        requested_model = $ModelId
        provider_profile = $effectiveProviderProfile
        model_catalog_input = $modelCatalogInput
        openclaw_config = $configPath
        config_builder = $configBuilderPath
        config_generation_log = $configGenerationPath
        model_catalog_log = $modelsListPath
        model_catalog_exit_code = $modelListExitCode
        manifest = $manifestPath
        created_at = (Get-Date).ToString("o")
    }
    Write-Host "BLOCKED: requested model does not advertise image input: $ModelId"
    Write-Host "Experiment record: $experimentJson"
    exit 20
}

$gatewayProcess = $null
$exitCode = 1
$postprocessExitCode = 0
$evalAttempts = 0
$evalExitCode = 1
$evalErrorCount = 0
$status = "failed"

try {
    $gatewayProcess = Start-Process `
        -FilePath "node" `
        -ArgumentList @($openclawCli, "gateway", "run", "--verbose") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $gatewayOut `
        -RedirectStandardError $gatewayErr `
        -PassThru

    Start-Sleep -Seconds 8

    $evalArgs = @(
        "run", "python", "scripts\run-eval.py",
        "--gateway", "ws://127.0.0.1:18789",
        "--manifest", $manifestPath,
        "--timeout-sec", [string]$TimeoutSec,
        "--output", $evalDir
    )
    if ($Limit -gt 0) {
        $evalArgs += @("--limit", [string]$Limit)
    }
    if ($RequirePerfect) {
        $evalArgs += "--require-perfect"
    }
    if ($MultiPass) {
        $evalArgs += @(
            "--multi-pass",
            "--multi-pass-max-targets",
            [string]$MultiPassMaxTargets,
            "--multi-pass-max-ekg-systematic-probes",
            [string]$MultiPassMaxEkgSystematicProbes
        )
    }

    Write-ExperimentJson $experimentJson @{
        status = "running"
        requested_model = $ModelId
        provider_profile = $effectiveProviderProfile
        timeout_sec = $TimeoutSec
        limit = $Limit
        multi_pass = [bool]$MultiPass
        multi_pass_max_targets = $MultiPassMaxTargets
        multi_pass_max_ekg_systematic_probes = $MultiPassMaxEkgSystematicProbes
        require_perfect = [bool]$RequirePerfect
        manifest = $manifestPath
        experiment_dir = $experimentDir
        openclaw_config = $configPath
        config_builder = $configBuilderPath
        config_generation_log = $configGenerationPath
        model_catalog_log = $modelsListPath
        model_catalog_exit_code = $modelListExitCode
        model_catalog_warning = $modelCatalogWarning
        gateway_stdout = $gatewayOut
        gateway_stderr = $gatewayErr
        eval_console = $evalOut
        eval_artifacts = $evalDir
        scorecard_rebuilt = $scorecardRebuilt
        review_artifacts = $reviewDir
        started_at = $stamp
        updated_at = (Get-Date).ToString("o")
    }

    $evalResult = Invoke-EvalWithGatewayRetry -EvalArgs $evalArgs
    $evalOutput = $evalResult.Output
    $evalExitCode = $evalResult.ExitCode
    $evalAttempts = $evalResult.Attempts
    $exitCode = $evalExitCode
    $postOutput = @()
    $resultsDir = Join-Path $evalDir "results"
    if (Test-Path $resultsDir) {
        $postOutput += ""
        $postOutput += "=== rebuild scorecard ==="
        $rebuildResult = Invoke-NativeCommand `
            -FilePath "uv" `
            -Arguments @(
                "run", "python", "scripts\rebuild-eval-scorecard.py",
                "--eval-dir", $evalDir,
                "--manifest", $manifestPath,
                "--output", $scorecardRebuilt
            )
        $postOutput += $rebuildResult.Output
        $rebuildExitCode = $rebuildResult.ExitCode
        $postOutput += ""
        $postOutput += "=== export annotations ==="
        $exportResult = Invoke-NativeCommand `
            -FilePath "uv" `
            -Arguments @(
                "run", "python", "scripts\export-eval-annotations.py",
                "--eval-dir", $evalDir,
                "--manifest", $manifestPath,
                "--output", $reviewDir
            )
        $postOutput += $exportResult.Output
        $exportExitCode = $exportResult.ExitCode
        if ($rebuildExitCode -ne 0 -or $exportExitCode -ne 0) {
            $postprocessExitCode = 1
        }
    }
    if (Test-Path $scorecardPath) {
        try {
            $scorecard = Get-Content $scorecardPath -Raw | ConvertFrom-Json
            $evalErrorCount = [int]$scorecard.error_count
        }
        catch {
            $evalErrorCount = 1
            $postprocessExitCode = 1
            $postOutput += ""
            $postOutput += "Could not read eval error_count from scorecard.json: $_"
        }
    }
    elseif ($evalExitCode -eq 0) {
        $evalErrorCount = 1
        $postprocessExitCode = 1
        $postOutput += ""
        $postOutput += "Missing eval scorecard.json after successful eval exit."
    }
    if ($evalExitCode -eq 0 -and $evalErrorCount -gt 0) {
        $exitCode = 1
    }
    @($evalOutput) + @($postOutput) | Set-Content -Path $evalOut -Encoding UTF8
    $status = if ($exitCode -eq 0 -and $postprocessExitCode -eq 0 -and $evalErrorCount -eq 0) {
        "completed"
    } else {
        "completed_with_failures"
    }
}
finally {
    if ($gatewayProcess -and -not $gatewayProcess.HasExited) {
        Stop-Process -Id $gatewayProcess.Id -Force
    }
    Write-ExperimentJson $experimentJson @{
        status = $status
        requested_model = $ModelId
        provider_profile = $effectiveProviderProfile
        timeout_sec = $TimeoutSec
        limit = $Limit
        multi_pass = [bool]$MultiPass
        multi_pass_max_targets = $MultiPassMaxTargets
        multi_pass_max_ekg_systematic_probes = $MultiPassMaxEkgSystematicProbes
        require_perfect = [bool]$RequirePerfect
        exit_code = $exitCode
        eval_exit_code = $evalExitCode
        eval_error_count = $evalErrorCount
        manifest = $manifestPath
        experiment_dir = $experimentDir
        openclaw_config = $configPath
        config_builder = $configBuilderPath
        config_generation_log = $configGenerationPath
        model_catalog_log = $modelsListPath
        model_catalog_exit_code = $modelListExitCode
        model_catalog_warning = $modelCatalogWarning
        eval_attempts = $evalAttempts
        gateway_stdout = $gatewayOut
        gateway_stderr = $gatewayErr
        eval_console = $evalOut
        eval_artifacts = $evalDir
        scorecard_rebuilt = $scorecardRebuilt
        review_artifacts = $reviewDir
        postprocess_exit_code = $postprocessExitCode
        started_at = $stamp
        finished_at = (Get-Date).ToString("o")
    }
    Write-Host "Experiment record: $experimentJson"
}

exit $exitCode
