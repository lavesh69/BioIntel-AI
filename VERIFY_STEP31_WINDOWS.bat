@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe scripts\seed_step31_data_ui_foundation.py || exit /b 1
.venv\Scripts\python.exe scripts\verify_step31.py || exit /b 1
.venv\Scripts\python.exe -m pytest -q tests\test_step31_scientific_data_ui.py || exit /b 1
echo.
echo BioIntel AI Step 31 scientific data and UI verification passed.
pause
