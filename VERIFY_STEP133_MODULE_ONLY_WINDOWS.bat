@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step133_module_only.py
) else (
  python scripts\verify_step133_module_only.py
)
if errorlevel 1 (
  echo.
  echo STEP 133 MODULE-ONLY VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo STEP 133 MODULE-ONLY VERIFICATION PASSED
pause
