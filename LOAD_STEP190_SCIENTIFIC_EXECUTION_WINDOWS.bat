@echo off
setlocal
cd /d "%~dp0"
echo [BioIntel AI] Building Step 190 Scientific Execution and Interoperability assets...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\step190_build_scientific_execution.py
  if errorlevel 1 goto :fail
  ".venv\Scripts\python.exe" scripts\step190_verify_scientific_execution.py
  if errorlevel 1 goto :fail
) else (
  python scripts\step190_build_scientific_execution.py
  if errorlevel 1 goto :fail
  python scripts\step190_verify_scientific_execution.py
  if errorlevel 1 goto :fail
)
echo Step 190 completed successfully.
exit /b 0
:fail
echo Step 190 failed. Review the error above and the generated diagnostics.
exit /b 1
