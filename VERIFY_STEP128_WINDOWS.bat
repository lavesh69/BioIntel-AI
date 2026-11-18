@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
%PY% scripts\verify_step128.py
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Step 128 verification failed. Review reports\step128_next_generation_verification.json
  pause
  exit /b %RC%
)
echo.
echo Step 128 verification passed.
pause
exit /b 0
