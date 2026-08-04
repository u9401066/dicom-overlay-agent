@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-ecgfounder-sidecar.ps1" %*
exit /b %ERRORLEVEL%
