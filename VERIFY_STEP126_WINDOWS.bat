@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo BioIntel AI Step 126 Verification
echo Artistic Aesthetic Theme Collection
echo ============================================================
if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
"%PYTHON_EXE%" scripts\verify_step126.py
if errorlevel 1 (
  echo.
  echo STEP 126 VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo STEP 126 VERIFICATION PASSED
pause
endlocal
