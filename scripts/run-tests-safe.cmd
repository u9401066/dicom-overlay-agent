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
set "DICOM_OVERLAY_TEST_DISABLE_REAL_OPENCLAW=1"
set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
set "PYTEST_RUN_LOCK=%REPO_ROOT%\data\tmp\pytest-run.lock"

if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%REPO_ROOT%\data\tmp" mkdir "%REPO_ROOT%\data\tmp"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Missing uv-managed virtualenv Python: "%PYTHON_EXE%"
    echo [ERROR] Create it once with: uv sync --group dev
    exit /b 74
)

mkdir "%PYTEST_RUN_LOCK%" 2>nul
if errorlevel 1 (
    echo [ERROR] Another pytest command is already running: "%PYTEST_RUN_LOCK%"
    exit /b 75
)

pushd "%REPO_ROOT%" || (
    rmdir "%PYTEST_RUN_LOCK%" 2>nul
    exit /b 1
)
"%PYTHON_EXE%" -m pytest -p no:cacheprovider --basetemp "%PYTEST_BASETEMP%" %PYTEST_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"
popd
rmdir "%PYTEST_RUN_LOCK%" 2>nul

exit /b %EXIT_CODE%
