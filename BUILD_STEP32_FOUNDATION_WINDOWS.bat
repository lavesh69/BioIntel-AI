@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\build_step32_foundation.py
) else (
  python scripts\build_step32_foundation.py
)
if errorlevel 1 (
  echo Step 32 foundation build failed.
  exit /b 1
)
echo Step 32 foundation rebuilt successfully.
pause
