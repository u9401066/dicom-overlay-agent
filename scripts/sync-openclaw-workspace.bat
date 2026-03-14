@echo off
setlocal

set "REPO_ROOT=%~dp0..\"
pushd "%REPO_ROOT%"

set "OPENCLAW_HOME=%CD%\openclaw-home"
set "SRC_SKILLS=%CD%\openclaw\workspace\skills"
set "DST_SKILLS=%OPENCLAW_HOME%\.openclaw\workspace\skills"

if not exist "%OPENCLAW_HOME%" mkdir "%OPENCLAW_HOME%"
if not exist "%OPENCLAW_HOME%\.openclaw" mkdir "%OPENCLAW_HOME%\.openclaw"
if not exist "%OPENCLAW_HOME%\.openclaw\workspace" mkdir "%OPENCLAW_HOME%\.openclaw\workspace"
if not exist "%DST_SKILLS%" mkdir "%DST_SKILLS%"

echo [INFO] Syncing workspace skills to %DST_SKILLS%
robocopy "%SRC_SKILLS%" "%DST_SKILLS%" /MIR /NFL /NDL /NJH /NJS /NP >nul
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
    echo [ERROR] robocopy failed with code %RC%
    popd
    exit /b %RC%
)

echo [OK] Workspace skills synced.
popd
exit /b 0