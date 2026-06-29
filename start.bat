@echo off
setlocal

set "REPO_ROOT=%~dp0"

REM Gateway is now auto-managed by Python — just launch the agent.
cd /d "%REPO_ROOT%"
call scripts\load-env.bat
.venv\Scripts\python.exe -m dicom_overlay --config config.yaml
