@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)
%PYTHON% scripts\verify_step60.py --root .
if errorlevel 1 (
  echo.
  echo Step 60 verification FAILED.
  pause
  exit /b 1
)
echo.
echo Step 60 verification PASSED.
pause
