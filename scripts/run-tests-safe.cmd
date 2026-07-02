@echo off
setlocal

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"

set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache-codex"
set "UV_NO_PROGRESS=1"
set "UV_PYTHON_DOWNLOADS=never"
set "TMP=%REPO_ROOT%\data\tmp\pytest-safe"
set "TEMP=%REPO_ROOT%\data\tmp\pytest-safe"
set "PYTEST_BASETEMP=%TEMP%\basetemp-%RANDOM%-%RANDOM%"
set "PYTEST_ARGS=tests/unit tests/smoke"
if not "%~1"=="" set "PYTEST_ARGS=%*"
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
uv run python -m pytest -p no:cacheprovider --basetemp "%PYTEST_BASETEMP%" %PYTEST_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"
popd
rmdir "%UV_RUN_LOCK%" 2>nul

exit /b %EXIT_CODE%
