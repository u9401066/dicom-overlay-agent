@echo off
setlocal

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"

set "UV_CACHE_DIR=%REPO_ROOT%\.uv-cache-codex"
set "UV_NO_PROGRESS=1"
set "UV_PYTHON_DOWNLOADS=never"
set "TMP=%REPO_ROOT%\data\tmp\pytest-safe"
set "TEMP=%REPO_ROOT%\data\tmp\pytest-safe"
set "PYTEST_BASETEMP=%TEMP%\basetemp"

if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%TEMP%" mkdir "%TEMP%"

pushd "%REPO_ROOT%" || exit /b 1
uv run python -m pytest -p no:cacheprovider --basetemp "%PYTEST_BASETEMP%" tests/unit tests/smoke %*
set "EXIT_CODE=%ERRORLEVEL%"
popd

exit /b %EXIT_CODE%
