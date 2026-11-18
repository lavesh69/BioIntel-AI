@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_education_phase5.py
) else if exist "runtime\python\python.exe" (
  "runtime\python\python.exe" scripts\verify_education_phase5.py
) else (
  py -3.11 scripts\verify_education_phase5.py
)
if errorlevel 1 (
  echo.
  echo Phase 5 verification FAILED.
  pause
  exit /b 1
)
echo.
echo Phase 5 verification PASSED.
pause
