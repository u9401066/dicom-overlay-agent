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
set "MEETI_RUN_LOCK=%REPO_ROOT%\data\tmp\meeti-run.lock"

if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%REPO_ROOT%\data\tmp" mkdir "%REPO_ROOT%\data\tmp"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Missing uv-managed virtualenv Python: "%PYTHON_EXE%"
    echo [ERROR] Create it once with: uv sync --group dev
    exit /b 74
)

mkdir "%MEETI_RUN_LOCK%" 2>nul
if errorlevel 1 (
    echo [ERROR] Another MEETI experiment command is already running: "%MEETI_RUN_LOCK%"
    exit /b 75
)

pushd "%REPO_ROOT%" || (
    rmdir "%MEETI_RUN_LOCK%" 2>nul
    exit /b 1
)
"%PYTHON_EXE%" scripts\run-meeti-openclaw-experiment.py %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
rmdir "%MEETI_RUN_LOCK%" 2>nul

exit /b %EXIT_CODE%
