@echo off
setlocal

set "REPO_ROOT=%~dp0"

REM Gateway is now auto-managed by Python — just launch the agent.
cd /d "%REPO_ROOT%"
call scripts\load-env.bat
REM A console can cover the viewer ROI; the desktop app logs to its file.
start "" ".venv\Scripts\pythonw.exe" -m dicom_overlay --config config.yaml
