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

echo [INFO] Fetching portable Node.js runtime for zero-install bundle...
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch-node.ps1
if errorlevel 1 (
    echo [ERROR] Portable Node.js fetch failed; refusing an incomplete bundle.
    popd
    exit /b 1
)

echo [INFO] Installing repo-local OpenClaw package for bundling...
set "FORCE_OPENCLAW_INSTALL=1"
call scripts\install-openclaw-local.bat
set "FORCE_OPENCLAW_INSTALL="
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

echo [INFO] Building DICOMOverlayAgent.exe...
call .venv\Scripts\python.exe -m PyInstaller --clean --noconfirm dicom-overlay-agent.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    popd
    exit /b 1
)

echo [OK] Built dist\DICOMOverlayAgent\DICOMOverlayAgent.exe

echo [INFO] Verifying packaged runtime, skills, rules, size, and self-check...
call .venv\Scripts\python.exe scripts\verify-packaged-app.py --bundle dist\DICOMOverlayAgent
if errorlevel 1 (
    echo [ERROR] Packaged application verification failed.
    popd
    exit /b 1
)

echo [OK] Bundle manifest: dist\DICOMOverlayAgent\bundle-manifest.json
popd
exit /b 0
