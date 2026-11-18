@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PYTHONDONTWRITEBYTECODE=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step134.py --pages
) else (
  python scripts\verify_step134.py --pages
)
if errorlevel 1 (
  echo.
  echo STEP 134 FULL MODULE VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo STEP 134 FULL MODULE VERIFICATION PASSED
pause
