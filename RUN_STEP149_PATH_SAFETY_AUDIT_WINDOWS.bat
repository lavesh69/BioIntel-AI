@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\step149_path_safety_audit.py" --root "."
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" (echo PATH SAFETY AUDIT PASSED.) else (echo PATH SAFETY AUDIT FAILED.)
pause
exit /b %RC%
