@echo off
setlocal

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"

set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache-codex"
set "UV_NO_PROGRESS=1"
set "UV_PYTHON_DOWNLOADS=never"
set "TMP=%REPO_ROOT%\data\tmp\uv"
set "TEMP=%REPO_ROOT%\data\tmp\uv"
set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
set "READINESS_RUN_LOCK=%REPO_ROOT%\data\tmp\readiness-run.lock"

if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%REPO_ROOT%\data\tmp" mkdir "%REPO_ROOT%\data\tmp"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Missing uv-managed virtualenv Python: "%PYTHON_EXE%"
    echo [ERROR] Create it once with: uv sync --group dev
    exit /b 74
)

mkdir "%READINESS_RUN_LOCK%" 2>nul
if errorlevel 1 (
    echo [ERROR] Another readiness command is already running: "%READINESS_RUN_LOCK%"
    exit /b 75
)

pushd "%REPO_ROOT%" || (
    rmdir "%READINESS_RUN_LOCK%" 2>nul
    exit /b 1
)
"%PYTHON_EXE%" scripts\check-real-model-readiness.py %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
rmdir "%READINESS_RUN_LOCK%" 2>nul

exit /b %EXIT_CODE%
