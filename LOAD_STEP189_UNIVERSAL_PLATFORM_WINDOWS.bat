@echo off
setlocal
cd /d "%~dp0"
echo [BioIntel AI] Building Step 189 Universal Production Platform...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\step189_build_universal_platform.py
  if errorlevel 1 goto :fail
  ".venv\Scripts\python.exe" scripts\step189_verify_universal_platform.py
) else (
  python scripts\step189_build_universal_platform.py
  if errorlevel 1 goto :fail
  python scripts\step189_verify_universal_platform.py
)
if errorlevel 1 goto :fail
echo Step 189 qualification completed successfully.
pause
exit /b 0
:fail
echo Step 189 qualification failed. Review STEP189_VERIFICATION.json.
pause
exit /b 1
