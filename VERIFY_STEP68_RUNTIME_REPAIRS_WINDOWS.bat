@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step68_runtime_repairs.py
) else (
  python scripts\verify_step68_runtime_repairs.py
)
set EXIT_CODE=%ERRORLEVEL%
pause
exit /b %EXIT_CODE%
