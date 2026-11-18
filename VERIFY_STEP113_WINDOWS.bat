@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

echo ============================================================
echo BioIntel AI Step 113 - Local Verification
echo ============================================================

if not exist "VERSION" (
  echo [ERROR] Run this file from the extracted BioIntel-AI folder.
  pause
  exit /b 1
)

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

"%PYTHON%" scripts\step97_self_test.py --root "%CD%" --output reports\step113_windows_self_test.json
if errorlevel 1 (
  echo [ERROR] Verification failed. Review reports\step113_windows_self_test.json
  pause
  exit /b 1
)

echo [OK] Step 113 verification passed.
pause
exit /b 0
