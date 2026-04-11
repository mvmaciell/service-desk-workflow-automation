@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run-visible-monitor.ps1"
echo.
pause
endlocal
