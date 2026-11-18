@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run INSTALL_WINDOWS.bat first.& pause& exit /b 1)
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe scripts\seed_step30_scientific_foundation.py || exit /b 1
echo Step 30 scaled biotechnology and bioinformatics reference datasets loaded.
pause
