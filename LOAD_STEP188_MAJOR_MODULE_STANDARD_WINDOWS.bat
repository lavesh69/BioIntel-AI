@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] BioIntel AI virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
echo Building Step 188 Universal Major Module Standard...
".venv\Scripts\python.exe" scripts\step188_build_major_module_standard.py
if errorlevel 1 goto :fail
echo Verifying all 80 major modules...
".venv\Scripts\python.exe" scripts\step188_verify_major_module_standard.py
if errorlevel 1 goto :fail
echo [PASS] Step 188 major-module standard is ready.
pause
exit /b 0
:fail
echo [ERROR] Step 188 build or verification failed. Review the message above.
pause
exit /b 1
