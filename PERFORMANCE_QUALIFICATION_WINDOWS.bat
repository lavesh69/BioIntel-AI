@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run INSTALL_WINDOWS.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\performance_qualification.py
endlocal
