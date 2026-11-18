@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Install BioIntel AI first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest -q tests\test_step92_advanced_tools.py tests\test_step93_innovation_modules.py tests\test_step94_pro_modules.py tests\test_step95_quality10_upgrade.py
if errorlevel 1 (
  echo Step 95 tests failed.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\verify_windows_wheelhouse.py --root "%CD%"
if errorlevel 1 (
  pause
  exit /b 1
)
echo Step 95 release-specific qualification passed.
pause
