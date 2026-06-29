param(
    [string]$ModelId = "openai/gpt-5.5-mini",
    [string]$ManifestPath = "",
    [int]$TimeoutSec = 90,
    [int]$Limit = 0,
    [string]$ExperimentDir = "",
    [switch]$MultiPass,
    [int]$MultiPassMaxTargets = 3,
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
$gatewayOut = Join-Path $experimentDir "gateway.stdout.log"
$gatewayErr = Join-Path $experimentDir "gateway.stderr.log"
$evalOut = Join-Path $experimentDir "eval-console.log"
$evalDir = Join-Path $experimentDir "eval"
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

$modelListOutput = & node $openclawCli models list 2>&1 | Out-String
$modelListOutput | Set-Content -Path $modelsListPath -Encoding UTF8

if ($modelListOutput -notmatch [regex]::Escape($ModelId)) {
    Write-ExperimentJson $experimentJson @{
        status = "blocked"
        reason = "requested model id is not exposed by the local OpenClaw catalog"
        requested_model = $ModelId
        suggested_models = @("openai/gpt-5.4-mini", "openai/gpt-5.5", "openai/gpt-5.5-pro")
        model_catalog_log = $modelsListPath
        manifest = $manifestPath
        created_at = (Get-Date).ToString("o")
    }
    Write-Host "BLOCKED: requested model is not in OpenClaw model catalog: $ModelId"
    Write-Host "Experiment record: $experimentJson"
    exit 20
}

$config = Get-Content $baseConfigPath -Raw | ConvertFrom-Json
$config.agents.defaults.model.primary = $ModelId
$modelsObj = $config.agents.defaults.models
if (-not ($modelsObj.PSObject.Properties.Name -contains $ModelId)) {
    $modelsObj | Add-Member -NotePropertyName $ModelId -NotePropertyValue @{
        alias = $ModelId
    } -Force
}
$config | ConvertTo-Json -Depth 20 | Set-Content -Path $configPath -Encoding UTF8
$env:OPENCLAW_CONFIG_PATH = $configPath

$gatewayProcess = $null
$exitCode = 1
$postprocessExitCode = 0
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
            [string]$MultiPassMaxTargets
        )
    }

    Write-ExperimentJson $experimentJson @{
        status = "running"
        requested_model = $ModelId
        timeout_sec = $TimeoutSec
        limit = $Limit
        multi_pass = [bool]$MultiPass
        multi_pass_max_targets = $MultiPassMaxTargets
        require_perfect = [bool]$RequirePerfect
        manifest = $manifestPath
        experiment_dir = $experimentDir
        openclaw_config = $configPath
        model_catalog_log = $modelsListPath
        gateway_stdout = $gatewayOut
        gateway_stderr = $gatewayErr
        eval_console = $evalOut
        eval_artifacts = $evalDir
        scorecard_rebuilt = $scorecardRebuilt
        review_artifacts = $reviewDir
        started_at = $stamp
        updated_at = (Get-Date).ToString("o")
    }

    $evalOutput = & uv @evalArgs 2>&1
    $exitCode = $LASTEXITCODE
    $postOutput = @()
    $resultsDir = Join-Path $evalDir "results"
    if (Test-Path $resultsDir) {
        $postOutput += ""
        $postOutput += "=== rebuild scorecard ==="
        $postOutput += & uv run python scripts\rebuild-eval-scorecard.py `
            --eval-dir $evalDir `
            --manifest $manifestPath `
            --output $scorecardRebuilt 2>&1
        $rebuildExitCode = $LASTEXITCODE
        $postOutput += ""
        $postOutput += "=== export annotations ==="
        $postOutput += & uv run python scripts\export-eval-annotations.py `
            --eval-dir $evalDir `
            --manifest $manifestPath `
            --output $reviewDir 2>&1
        $exportExitCode = $LASTEXITCODE
        if ($rebuildExitCode -ne 0 -or $exportExitCode -ne 0) {
            $postprocessExitCode = 1
        }
    }
    @($evalOutput) + @($postOutput) | Set-Content -Path $evalOut -Encoding UTF8
    $status = if ($exitCode -eq 0 -and $postprocessExitCode -eq 0) {
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
        timeout_sec = $TimeoutSec
        limit = $Limit
        multi_pass = [bool]$MultiPass
        multi_pass_max_targets = $MultiPassMaxTargets
        require_perfect = [bool]$RequirePerfect
        exit_code = $exitCode
        manifest = $manifestPath
        experiment_dir = $experimentDir
        openclaw_config = $configPath
        model_catalog_log = $modelsListPath
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
