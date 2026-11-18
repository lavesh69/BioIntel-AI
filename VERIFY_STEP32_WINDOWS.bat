@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step32.py
) else (
  python scripts\verify_step32.py
)
if errorlevel 1 (
  echo Step 32 verification failed.
  exit /b 1
)
echo Step 32 verification passed.
pause
