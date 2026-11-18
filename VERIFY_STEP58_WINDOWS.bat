@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)
%PYTHON% scripts\verify_step58.py --root .
if errorlevel 1 (
  echo.
  echo Step 58 verification FAILED.
  pause
  exit /b 1
)
echo.
echo Step 58 verification PASSED.
pause
