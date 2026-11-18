@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "venv\Scripts\python.exe" set "PYTHON_EXE=venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

echo ============================================================
echo BioIntel AI Step 124 Premium Visual System Verification
echo ============================================================
"%PYTHON_EXE%" scripts\verify_step124.py
if errorlevel 1 (
  echo.
  echo STEP 124 VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo STEP 124 VERIFICATION PASSED
pause
exit /b 0
