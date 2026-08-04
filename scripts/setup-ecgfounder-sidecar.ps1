[CmdletBinding()]
param(
    [string]$RuntimeDir = "data\external\ecgfounder-runtime",
    [string]$PythonVersion = "3.11",
    [string]$MirrorAddress = "133.242.169.68",
    [switch]$DisableMirrorFallback,
    [switch]$SkipCheckpoint
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ResolvedRuntime = if ([IO.Path]::IsPathRooted($RuntimeDir)) {
    [IO.Path]::GetFullPath($RuntimeDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $RepoRoot $RuntimeDir))
}
$VenvDir = Join-Path $ResolvedRuntime ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$CheckpointDir = Join-Path $ResolvedRuntime "checkpoints"
$Checkpoint = Join-Path $CheckpointDir "12_lead_ECGFounder.pth"
$ExpectedHash = "ee199f3781f4ae1f732973267f003da0a759ea12bddb0dd28a77faa60aca7997"
$CheckpointUrl = "https://huggingface.co/PKUDigitalHealth/ECGFounder/resolve/main/12_lead_ECGFounder.pth?download=true"
$MirrorUrl = "https://hf-mirror.com/PKUDigitalHealth/ECGFounder/resolve/main/12_lead_ECGFounder.pth?download=true"
$Requirements = Join-Path $RepoRoot "sidecars\ecgfounder\requirements.txt"

New-Item -ItemType Directory -Force -Path $ResolvedRuntime | Out-Null
New-Item -ItemType Directory -Force -Path $CheckpointDir | Out-Null

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    & uv venv $VenvDir --python $PythonVersion --no-python-downloads
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the ECGFounder Python environment."
    }
}

& uv pip install --python $PythonExe --requirement $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "Could not install NumPy/SciPy into the ECGFounder environment."
}

& uv pip install --python $PythonExe "torch==2.4.0" `
    --index "https://download.pytorch.org/whl/cpu" `
    --index-strategy unsafe-best-match
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the official PyTorch CPU wheel."
}

if (-not $SkipCheckpoint) {
    $CheckpointReady = $false
    if (Test-Path -LiteralPath $Checkpoint -PathType Leaf) {
        $CurrentHash = (Get-FileHash -LiteralPath $Checkpoint -Algorithm SHA256).Hash.ToLowerInvariant()
        $CheckpointReady = $CurrentHash -eq $ExpectedHash
        if (-not $CheckpointReady) {
            throw "Existing ECGFounder checkpoint has an unexpected SHA-256."
        }
    }
    if (-not $CheckpointReady) {
        $Download = "$Checkpoint.download"
        if (Test-Path -LiteralPath $Download -PathType Leaf) {
            Remove-Item -LiteralPath $Download -Force
        }
        Write-Host "Downloading the pinned checkpoint from Hugging Face..."
        & curl.exe -fL --retry 3 --retry-delay 5 --connect-timeout 30 `
            --output $Download $CheckpointUrl
        $DownloadSucceeded = $LASTEXITCODE -eq 0
        if (-not $DownloadSucceeded -and -not $DisableMirrorFallback) {
            if (Test-Path -LiteralPath $Download -PathType Leaf) {
                Remove-Item -LiteralPath $Download -Force
            }
            Write-Warning "The official endpoint failed; trying the hash-gated mirror transport."
            & curl.exe -fL --retry 3 --retry-delay 5 --connect-timeout 30 `
                --resolve "hf-mirror.com:443:$MirrorAddress" `
                --output $Download $MirrorUrl
            $DownloadSucceeded = $LASTEXITCODE -eq 0
        }
        if (-not $DownloadSucceeded) {
            if (Test-Path -LiteralPath $Download -PathType Leaf) {
                Remove-Item -LiteralPath $Download -Force
            }
            throw "Could not download the pinned ECGFounder checkpoint."
        }
        $DownloadedHash = (Get-FileHash -LiteralPath $Download -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($DownloadedHash -ne $ExpectedHash) {
            Remove-Item -LiteralPath $Download -Force
            throw "Downloaded ECGFounder checkpoint failed SHA-256 verification."
        }
        Move-Item -LiteralPath $Download -Destination $Checkpoint
    }
}

& $PythonExe -c "import numpy, scipy, torch; print('numpy=' + numpy.__version__ + ' scipy=' + scipy.__version__ + ' torch=' + torch.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "ECGFounder runtime import self-check failed."
}

Write-Host "ECGFounder sidecar runtime ready."
Write-Host "Python: $PythonExe"
Write-Host "Checkpoint: $Checkpoint"
