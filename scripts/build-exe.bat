@echo off
setlocal

set "REPO_ROOT=%~dp0..\"
pushd "%REPO_ROOT%"

where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv not found on PATH.
    popd
    exit /b 1
)

echo [INFO] Installing Python build dependencies...
call uv sync --extra build
if errorlevel 1 (
    echo [ERROR] uv sync failed.
    popd
    exit /b 1
)

echo [INFO] Installing repo-local OpenClaw package for bundling...
call scripts\install-openclaw-local.bat
if errorlevel 1 (
    echo [ERROR] OpenClaw install failed.
    popd
    exit /b 1
)

echo [INFO] Staging slim OpenClaw runtime for bundling...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stage-openclaw-runtime.ps1
if errorlevel 1 (
    echo [ERROR] OpenClaw runtime staging failed.
    popd
    exit /b 1
)

echo [INFO] Fetching portable Node.js runtime for zero-install bundle...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch-node.ps1
if errorlevel 1 (
    echo [WARN] Portable Node.js fetch failed; bundle will rely on system Node.js.
)

echo [INFO] Building DICOMOverlayAgent.exe...
call .venv\Scripts\pyinstaller.exe --clean --noconfirm dicom-overlay-agent.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    popd
    exit /b 1
)

echo [OK] Built dist\DICOMOverlayAgent\DICOMOverlayAgent.exe
popd
exit /b 0
