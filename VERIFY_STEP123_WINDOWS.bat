@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Virtual environment missing. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\verify_step123.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Step 123 verification failed. Review reports\step123_verification.json
  pause
  exit /b %RC%
)
echo Step 123 verification passed.
pause
exit /b 0
