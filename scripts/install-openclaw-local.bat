@echo off
setlocal EnableDelayedExpansion

set "REPO_ROOT=%~dp0..\"
pushd "%REPO_ROOT%"

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm not found. Install a supported Node.js/npm toolchain first.
    popd
    exit /b 1
)

if not exist "openclaw" mkdir "openclaw"
if not exist "openclaw\package.json" (
    echo [ERROR] Missing openclaw\package.json.
    popd
    exit /b 1
)
for /f "delims=" %%p in ('where npm.cmd') do if not defined NPM_CMD_PATH set "NPM_CMD_PATH=%%p"
for %%p in ("!NPM_CMD_PATH!") do set "NPM_ROOT=%%~dpp"
set "NPM_CLI_JS=!NPM_ROOT!node_modules\npm\bin\npm-cli.js"
if not exist "openclaw-home" mkdir "openclaw-home"
if not exist "openclaw-home\.openclaw" mkdir "openclaw-home\.openclaw"
if not exist "openclaw-home\.openclaw\workspace" mkdir "openclaw-home\.openclaw\workspace"

set "MIN_SAFE_OPENCLAW_VERSION=2026.4.22"
for /f "usebackq delims=" %%v in (`node -p "require('./openclaw/package.json').dependencies.openclaw"`) do set "DESIRED_OPENCLAW_VERSION=%%v"

if not "%FORCE_OPENCLAW_INSTALL%"=="1" (
    if exist "openclaw\node_modules\openclaw\package.json" (
        echo [INFO] Checking existing repo-local OpenClaw runtime ...
        for /f "usebackq delims=" %%v in (`node -p "require('./openclaw/node_modules/openclaw/package.json').version"`) do set "OPENCLAW_VERSION=%%v"
        if "!OPENCLAW_VERSION!"=="!DESIRED_OPENCLAW_VERSION!" (
            call :check_openclaw_version "!OPENCLAW_VERSION!"
            if errorlevel 1 (
                popd
                exit /b 1
            )
            echo [OK] Existing OpenClaw version !OPENCLAW_VERSION! matches the lock target.
            popd
            exit /b 0
        )
        echo [INFO] OpenClaw !OPENCLAW_VERSION! differs from target !DESIRED_OPENCLAW_VERSION!; reinstalling.
    )
)

if "%OPENCLAW_NPM_SPEC%"=="" (
    if not exist "openclaw\package-lock.json" (
        echo [ERROR] Missing openclaw\package-lock.json for reproducible npm ci.
        popd
        exit /b 1
    )
    echo [INFO] Installing locked OpenClaw !DESIRED_OPENCLAW_VERSION! with npm ci ...
    call :run_npm ci --prefix openclaw --omit=dev
) else (
    echo [INFO] Updating OpenClaw from explicit spec %OPENCLAW_NPM_SPEC% ...
    call :run_npm install --prefix openclaw --save-exact "%OPENCLAW_NPM_SPEC%"
)
if errorlevel 1 (
    echo [ERROR] Local OpenClaw install failed.
    popd
    exit /b 1
)

for /f "usebackq delims=" %%v in (`node -p "require('./openclaw/node_modules/openclaw/package.json').version"`) do set "OPENCLAW_VERSION=%%v"
for /f "usebackq delims=" %%v in (`node -p "require('./openclaw/package.json').dependencies.openclaw"`) do set "DESIRED_OPENCLAW_VERSION=%%v"
echo [INFO] Installed OpenClaw version: %OPENCLAW_VERSION%
if not "!OPENCLAW_VERSION!"=="!DESIRED_OPENCLAW_VERSION!" (
    echo [ERROR] Installed OpenClaw !OPENCLAW_VERSION! does not match lock target !DESIRED_OPENCLAW_VERSION!.
    popd
    exit /b 1
)
call :check_openclaw_version "!OPENCLAW_VERSION!"
if errorlevel 1 (
    popd
    exit /b 1
)

echo [OK] Local OpenClaw install complete.
echo [NEXT] Run start.bat to launch the local gateway + overlay agent.

popd
exit /b 0

:run_npm
if exist "node\node.exe" if exist "!NPM_CLI_JS!" (
    "node\node.exe" "!NPM_CLI_JS!" %*
    exit /b !errorlevel!
)
call npm %*
exit /b !errorlevel!

:check_openclaw_version
if exist "node\node.exe" (
    "node\node.exe" scripts\check-openclaw-version.cjs "%~1" "%MIN_SAFE_OPENCLAW_VERSION%"
    exit /b !errorlevel!
)
node scripts\check-openclaw-version.cjs "%~1" "%MIN_SAFE_OPENCLAW_VERSION%"
exit /b !errorlevel!
