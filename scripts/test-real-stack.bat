@echo off
setlocal

set "REPO_ROOT=%~dp0..\"
pushd "%REPO_ROOT%"

call scripts\install-openclaw-local.bat
if errorlevel 1 exit /b 1

call scripts\sync-openclaw-workspace.bat
if errorlevel 1 exit /b 1

set "OPENCLAW_HOME=%CD%\openclaw-home"
set "OPENCLAW_STATE_DIR=%OPENCLAW_HOME%"
set "OPENCLAW_CONFIG_PATH=%CD%\openclaw\openclaw.json"
set "HOME=%OPENCLAW_HOME%"
set "USERPROFILE=%OPENCLAW_HOME%"

echo [INFO] Validating OpenClaw config...
node .\openclaw\node_modules\openclaw\openclaw.mjs config validate
if errorlevel 1 exit /b 1

echo [INFO] Starting OpenClaw Gateway in background...
start "OpenClaw Gateway" cmd /k "set OPENCLAW_STATE_DIR=%OPENCLAW_STATE_DIR% && set OPENCLAW_CONFIG_PATH=%OPENCLAW_CONFIG_PATH% && set HOME=%HOME% && set USERPROFILE=%USERPROFILE% && node .\openclaw\node_modules\openclaw\openclaw.mjs gateway run --verbose"

timeout /t 5 /nobreak >nul

echo [INFO] Checking Gateway health...
node .\openclaw\node_modules\openclaw\openclaw.mjs gateway health
if errorlevel 1 exit /b 1

echo [INFO] Starting DICOM Overlay Agent...
start "DICOM Overlay Agent" cmd /k ".venv\Scripts\python.exe -m dicom_overlay --config config.yaml"

echo [OK] Real stack launched.
echo [NEXT] 1. Open your DICOM viewer.
echo [NEXT] 2. If prompted, complete ROI setup.
echo [NEXT] 3. Change images or click the control bar retrigger button.
echo [NEXT] 4. Watch OpenClaw Gateway and overlay windows for results.

popd
exit /b 0