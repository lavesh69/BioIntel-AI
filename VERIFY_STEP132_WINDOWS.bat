@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step132_visual_intelligence.py
) else (
  py -3.11 scripts\verify_step132_visual_intelligence.py
)
if errorlevel 1 (
  echo.
  echo STEP 132 VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo STEP 132 VERIFICATION PASSED
pause
