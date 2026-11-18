@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe scripts\seed_step30_scientific_foundation.py || exit /b 1
.venv\Scripts\python.exe scripts\verify_step29.py || exit /b 1
echo.
echo BioIntel AI Step 29 compatibility verification passed under Step 30.
pause
