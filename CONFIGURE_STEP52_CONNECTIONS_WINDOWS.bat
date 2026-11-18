@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\configure_step52_connections.ps1"
echo.
pause
