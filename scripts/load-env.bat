@echo off
REM Load repo-local .env values into the current cmd.exe environment.
REM Values are intentionally never echoed because they may contain API keys.

if not exist ".env" exit /b 0

for /f "usebackq eol=# tokens=1* delims==" %%A in (".env") do (
    if not "%%~A"=="" if not "%%~B"=="" set "%%~A=%%~B"
)

exit /b 0
