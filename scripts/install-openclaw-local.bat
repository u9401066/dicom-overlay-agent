@echo off
setlocal

set "REPO_ROOT=%~dp0..\"
pushd "%REPO_ROOT%"

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js 22+ first.
    popd
    exit /b 1
)

if not exist "openclaw" mkdir "openclaw"
if not exist "openclaw-home" mkdir "openclaw-home"
if not exist "openclaw-home\.openclaw" mkdir "openclaw-home\.openclaw"
if not exist "openclaw-home\.openclaw\workspace" mkdir "openclaw-home\.openclaw\workspace"

echo [INFO] Installing OpenClaw locally into .\openclaw\node_modules ...
call npm install --prefix openclaw
if errorlevel 1 (
    echo [ERROR] Local OpenClaw install failed.
    popd
    exit /b 1
)

echo [OK] Local OpenClaw install complete.
echo [NEXT] Run start.bat to launch the local gateway + overlay agent.

popd
exit /b 0