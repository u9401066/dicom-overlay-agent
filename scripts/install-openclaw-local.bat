@echo off
setlocal EnableDelayedExpansion

set "REPO_ROOT=%~dp0..\"
pushd "%REPO_ROOT%"

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js 22+ first.
    popd
    exit /b 1
)

if not exist "openclaw" mkdir "openclaw"
if not exist "openclaw\package.json" (
    echo [ERROR] Missing openclaw\package.json.
    popd
    exit /b 1
)
if not exist "openclaw-home" mkdir "openclaw-home"
if not exist "openclaw-home\.openclaw" mkdir "openclaw-home\.openclaw"
if not exist "openclaw-home\.openclaw\workspace" mkdir "openclaw-home\.openclaw\workspace"

if "%OPENCLAW_NPM_SPEC%"=="" set "OPENCLAW_NPM_SPEC=openclaw@latest"
set "MIN_SAFE_OPENCLAW_VERSION=2026.4.22"

if not "%FORCE_OPENCLAW_INSTALL%"=="1" (
    if exist "openclaw\node_modules\openclaw\package.json" (
        echo [INFO] Checking existing repo-local OpenClaw runtime ...
        for /f "usebackq delims=" %%v in (`node -p "require('./openclaw/node_modules/openclaw/package.json').version"`) do set "OPENCLAW_VERSION=%%v"
        node -e "const v='!OPENCLAW_VERSION!'.split('-')[0].split('.').map(Number); const m='%MIN_SAFE_OPENCLAW_VERSION%'.split('.').map(Number); const ok=(v[0]>m[0])||(v[0]===m[0]&&(v[1]>m[1]||(v[1]===m[1]&&v[2]>=m[2]))); process.exit(ok?0:1);"
        if not errorlevel 1 (
            echo [OK] Existing OpenClaw version !OPENCLAW_VERSION! is safe; skipping npm install.
            popd
            exit /b 0
        )
        echo [WARN] Existing OpenClaw version !OPENCLAW_VERSION! is older than %MIN_SAFE_OPENCLAW_VERSION%; reinstalling.
    )
)

echo [INFO] Installing %OPENCLAW_NPM_SPEC% locally into .\openclaw\node_modules ...
call npm install --prefix openclaw "%OPENCLAW_NPM_SPEC%"
if errorlevel 1 (
    echo [ERROR] Local OpenClaw install failed.
    popd
    exit /b 1
)

for /f "usebackq delims=" %%v in (`node -p "require('./openclaw/node_modules/openclaw/package.json').version"`) do set "OPENCLAW_VERSION=%%v"
echo [INFO] Installed OpenClaw version: %OPENCLAW_VERSION%
node -e "const v='%OPENCLAW_VERSION%'.split('-')[0].split('.').map(Number); const m='%MIN_SAFE_OPENCLAW_VERSION%'.split('.').map(Number); const ok=(v[0]>m[0])||(v[0]===m[0]&&(v[1]>m[1]||(v[1]===m[1]&&v[2]>=m[2]))); if(!ok){console.error('[ERROR] OpenClaw '+process.env.OPENCLAW_VERSION+' is older than safe minimum %MIN_SAFE_OPENCLAW_VERSION%.'); process.exit(1);}"
if errorlevel 1 (
    popd
    exit /b 1
)

echo [OK] Local OpenClaw install complete.
echo [NEXT] Run start.bat to launch the local gateway + overlay agent.

popd
exit /b 0
