@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo BioIntel virtual environment not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe scripts\seed_demo_workspace.py || exit /b 1
.venv\Scripts\python.exe scripts\seed_step29_bioinformatics.py || exit /b 1
echo.
echo BioIntel AI demonstration workspace loaded successfully.
pause
