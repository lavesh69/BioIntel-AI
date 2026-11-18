@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step122_protein_design.py
) else (
  python scripts\verify_step122_protein_design.py
)
if errorlevel 1 (
  echo.
  echo STEP 122 VERIFICATION FAILED
  exit /b 1
)
echo.
echo STEP 122 PROTEIN DESIGN VERIFICATION PASSED
endlocal
