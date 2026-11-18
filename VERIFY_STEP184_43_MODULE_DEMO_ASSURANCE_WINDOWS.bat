@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\step184_verify_demo_assurance.py
) else (
  python scripts\step184_verify_demo_assurance.py
)
if errorlevel 1 exit /b 1
echo Step 184 verification passed.
endlocal
