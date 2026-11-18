@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PYTHONDONTWRITEBYTECODE=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step135.py
) else (
  python scripts\verify_step135.py
)
if errorlevel 1 (
  echo.
  echo STEP 135 MODULE SCIENTIFIC VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo STEP 135 MODULE SCIENTIFIC VERIFICATION PASSED
pause
