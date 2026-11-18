@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo Generating complete data coverage and professional demo workspace...
call .venv\Scripts\python.exe scripts\generate_complete_coverage.py
if errorlevel 1 goto :error

echo.
echo Complete data coverage is ready.
echo Open Data Coverage Center in BioIntel AI.
pause
exit /b 0

:error
echo.
echo Coverage generation failed. Review the error above.
pause
exit /b 1
