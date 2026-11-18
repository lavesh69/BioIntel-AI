@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe scripts\test_connected_services.py --all
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE% EQU 0 (
  echo All requested connections passed.
) else (
  echo One or more connections failed. Open reports\step52_connection_test.json for details.
)
pause
exit /b %EXITCODE%
