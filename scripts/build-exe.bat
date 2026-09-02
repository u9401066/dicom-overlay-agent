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

echo [INFO] Verifying the frozen Python lockfile...
call uv lock --check
if errorlevel 1 (
    echo [ERROR] uv.lock is stale; refusing a non-reproducible build.
    popd
    exit /b 1
)

set "DICOM_OVERLAY_BUILD_ENV=%REPO_ROOT%.venv-build"
set "UV_PROJECT_ENVIRONMENT=%DICOM_OVERLAY_BUILD_ENV%"
set "DICOM_OVERLAY_RELEASE_PYTHON=3.13.12"

echo [INFO] Syncing an isolated frozen Python %DICOM_OVERLAY_RELEASE_PYTHON% runtime + build environment...
call uv sync --python "%DICOM_OVERLAY_RELEASE_PYTHON%" --frozen --no-dev --extra build
if errorlevel 1 (
    echo [ERROR] Frozen no-dev build environment sync failed.
    popd
    exit /b 1
)

where upx >nul 2>nul
if errorlevel 1 (
    set "DICOM_OVERLAY_UPX_ENABLED=0"
    echo [INFO] UPX unavailable; recording an explicit no-UPX size baseline.
) else (
    set "DICOM_OVERLAY_UPX_ENABLED=1"
    echo [INFO] UPX detected; compression must be observed by package verification.
)

echo [INFO] Recording exact package toolchain and compression intent...
call "%DICOM_OVERLAY_BUILD_ENV%\Scripts\python.exe" scripts\write-package-build-receipt.py --output build\package-build-receipt.json --upx-enabled %DICOM_OVERLAY_UPX_ENABLED%
if errorlevel 1 (
    echo [ERROR] Package build receipt failed.
    popd
    exit /b 1
)

echo [INFO] Validating and materializing the clinical knowledge registry...
call "%DICOM_OVERLAY_BUILD_ENV%\Scripts\python.exe" scripts\validate-clinical-knowledge.py --check-generated
if errorlevel 1 (
    echo [ERROR] Clinical knowledge generated views are stale or invalid.
    popd
    exit /b 1
)
call "%DICOM_OVERLAY_BUILD_ENV%\Scripts\python.exe" scripts\build-clinical-knowledge-sqlite.py --output build\clinical-knowledge.sqlite
if errorlevel 1 (
    echo [ERROR] Clinical knowledge SQLite build failed.
    popd
    exit /b 1
)
call "%DICOM_OVERLAY_BUILD_ENV%\Scripts\python.exe" scripts\build-clinical-knowledge-sqlite.py --output build\clinical-knowledge.sqlite --check
if errorlevel 1 (
    echo [ERROR] Clinical knowledge SQLite parity verification failed.
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
call "%DICOM_OVERLAY_BUILD_ENV%\Scripts\python.exe" -m PyInstaller --clean --noconfirm dicom-overlay-agent.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    popd
    exit /b 1
)

echo [OK] Built dist\DICOMOverlayAgent\DICOMOverlayAgent.exe

echo [INFO] Verifying packaged runtime, skills, rules, size, and self-check...
call "%DICOM_OVERLAY_BUILD_ENV%\Scripts\python.exe" scripts\verify-packaged-app.py --bundle dist\DICOMOverlayAgent
if errorlevel 1 (
    echo [ERROR] Packaged application verification failed.
    popd
    exit /b 1
)

echo [OK] Bundle manifest: dist\DICOMOverlayAgent\bundle-manifest.json
popd
exit /b 0
