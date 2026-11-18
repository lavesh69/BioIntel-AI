@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
%PY% scripts\verify_step127.py
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Step 127 verification failed. Review reports\step127_scientific_depth_verification.json
  pause
  exit /b %RC%
)
echo.
echo Step 127 verification passed.
pause
exit /b 0
