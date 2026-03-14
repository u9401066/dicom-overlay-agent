@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "OPENCLAW_HOME=%REPO_ROOT%openclaw-home"
set "OPENCLAW_STATE_DIR=%OPENCLAW_HOME%"
set "OPENCLAW_CONFIG_PATH=%REPO_ROOT%openclaw\openclaw.json"

if not exist "%OPENCLAW_HOME%" mkdir "%OPENCLAW_HOME%"
if not exist "%OPENCLAW_HOME%\.openclaw" mkdir "%OPENCLAW_HOME%\.openclaw"
if not exist "%OPENCLAW_HOME%\.openclaw\workspace" mkdir "%OPENCLAW_HOME%\.openclaw\workspace"

set "HOME=%OPENCLAW_HOME%"
set "USERPROFILE=%OPENCLAW_HOME%"

call "%REPO_ROOT%scripts\sync-openclaw-workspace.bat"
if errorlevel 1 exit /b 1

REM 1. 啟動 OpenClaw Gateway
if exist "openclaw\node_modules\openclaw\openclaw.mjs" (
    start "" /B cmd /c "set OPENCLAW_STATE_DIR=%OPENCLAW_STATE_DIR% && set OPENCLAW_CONFIG_PATH=%OPENCLAW_CONFIG_PATH% && set HOME=%HOME% && set USERPROFILE=%USERPROFILE% && node openclaw\node_modules\openclaw\openclaw.mjs gateway run --verbose"
) else (
    echo [WARN] workspace-local OpenClaw not found.
    echo [HINT] run scripts\install-openclaw-local.bat first.
    exit /b 1
)

REM 2. 等待 Gateway 啟動
timeout /t 3 /nobreak >nul

REM 3. 啟動 Overlay Agent
.venv\Scripts\python.exe -m dicom_overlay --config config.yaml
