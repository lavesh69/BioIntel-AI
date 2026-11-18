@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe scripts\seed_professional_databases.py || exit /b 1
.venv\Scripts\python.exe scripts\verify_step28.py || exit /b 1
echo.
echo BioIntel AI Step 28 verification passed.
pause
