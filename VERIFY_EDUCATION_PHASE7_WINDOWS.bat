@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
echo ============================================================
echo BioIntel AI Education Phase 7 Desktop Verification
echo ============================================================
set "PYTHON="
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON if exist "runtime\python\python.exe" set "PYTHON=runtime\python\python.exe"
if defined PYTHON goto run_verify
py -3.11 -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo ERROR: BioIntel Python runtime or Python 3.11 is unavailable.
  pause
  exit /b 1
)
set "PYTHON=py -3.11"
:run_verify
%PYTHON% scripts\verify_education_phase7.py
if errorlevel 1 goto failed
%PYTHON% -m compileall -q src\biointel\education pages\348_BioIntel_Education_Desktop.py
if errorlevel 1 goto failed
echo.
echo Phase 7 desktop verification PASSED.
pause
exit /b 0
:failed
echo.
echo Phase 7 desktop verification FAILED.
pause
exit /b 1
