@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
echo ============================================================
echo BioIntel AI Education Phase 8 Visual UI Verification
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
%PYTHON% scripts\verify_education_phase8.py
if errorlevel 1 goto failed
%PYTHON% -m compileall -q src\biointel\ui\product_experience_v8.py src\biointel\education src\biointel\connect\pro_ui.py src\biointel\shiro\ui\page.py pages\70_BioIntel_Studio.py
if errorlevel 1 goto failed
echo.
echo Phase 8 visual UI verification PASSED.
pause
exit /b 0
:failed
echo.
echo Phase 8 visual UI verification FAILED.
pause
exit /b 1
