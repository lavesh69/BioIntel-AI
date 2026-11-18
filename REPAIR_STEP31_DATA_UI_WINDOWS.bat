@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
set "PYTHONPATH=%CD%\src"
echo Rebuilding scientific registry completeness, lineage and UI indexes...
.venv\Scripts\python.exe scripts\seed_step31_data_ui_foundation.py || exit /b 1
echo.
echo Step 31 data and UI indexes repaired. No remote scientific records were fabricated or downloaded.
pause
