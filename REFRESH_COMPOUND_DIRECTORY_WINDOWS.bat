@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo Rebuilding the 5,000-name compound directory...
call .venv\Scripts\python.exe scripts\generate_common_compound_directory.py
if errorlevel 1 goto :error

echo.
echo Compound directory is ready.
pause
exit /b 0

:error
echo.
echo Compound-directory generation failed. Review the error above.
pause
exit /b 1
