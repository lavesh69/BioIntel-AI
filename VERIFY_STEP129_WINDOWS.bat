@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step129.py
) else (
  python scripts\verify_step129.py
)
if errorlevel 1 (
  echo STEP 129 VERIFICATION FAILED
  exit /b 1
)
echo STEP 129 VERIFICATION PASSED
endlocal
