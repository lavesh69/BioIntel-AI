@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
set "PYTHONPATH=%CD%\src"
echo Loading scaled scientific reference datasets and registry depth...
.venv\Scripts\python.exe scripts\seed_step30_scientific_foundation.py || exit /b 1
echo.
echo Step 30 scientific reference data loaded successfully.
pause
