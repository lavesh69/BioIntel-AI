@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\rollback_step96.ps1"
if errorlevel 1 (
  echo Rollback failed. Review the message above.
  pause
  exit /b 1
)
echo Rollback complete.
pause
