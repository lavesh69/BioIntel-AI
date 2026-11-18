@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
echo ============================================================
echo BioIntel AI Education Phase 6 Verification
ECHO ============================================================
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_education_phase6.py
) else if exist "runtime\python\python.exe" (
  "runtime\python\python.exe" scripts\verify_education_phase6.py
) else (
  py -3.11 scripts\verify_education_phase6.py
)
if errorlevel 1 (
  echo.
  echo Phase 6 verification FAILED.
  pause
  exit /b 1
)
echo.
echo Phase 6 verification PASSED.
pause
exit /b 0
