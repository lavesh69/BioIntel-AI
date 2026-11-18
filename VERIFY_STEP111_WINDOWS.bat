@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step111_native_integration.py
) else (
  python scripts\verify_step111_native_integration.py
)
set RC=%ERRORLEVEL%
if not "%RC%"=="0" echo Step 111 native integration verification reported one or more failures.
pause
exit /b %RC%
