@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step130_scientific_intelligence.py
) else (
  python scripts\verify_step130_scientific_intelligence.py
)
if errorlevel 1 (
  echo.
  echo STEP 130 VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo STEP 130 VERIFICATION PASSED
pause
endlocal
