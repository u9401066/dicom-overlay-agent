@echo off
setlocal

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"

set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache-codex"
set "UV_NO_PROGRESS=1"
set "UV_PYTHON_DOWNLOADS=never"
set "TMP=%REPO_ROOT%\data\tmp\uv"
set "TEMP=%REPO_ROOT%\data\tmp\uv"
set "UV_RUN_LOCK=%REPO_ROOT%\data\tmp\uv-run.lock"

if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%REPO_ROOT%\data\tmp" mkdir "%REPO_ROOT%\data\tmp"

mkdir "%UV_RUN_LOCK%" 2>nul
if errorlevel 1 (
    echo [ERROR] Another uv-backed command is already running: "%UV_RUN_LOCK%"
    exit /b 75
)

pushd "%REPO_ROOT%" || (
    rmdir "%UV_RUN_LOCK%" 2>nul
    exit /b 1
)
uv run python scripts\check-real-model-readiness.py %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
rmdir "%UV_RUN_LOCK%" 2>nul

exit /b %EXIT_CODE%
