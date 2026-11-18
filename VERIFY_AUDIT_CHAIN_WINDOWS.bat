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

if not exist reports\generated mkdir reports\generated

call .venv\Scripts\python.exe -m biointel audit-verify ^
  --output reports\generated\audit-integrity.json

if errorlevel 1 (
  echo Audit verification command failed.
  pause
  exit /b 1
)

echo.
echo Audit integrity report:
echo %CD%\reports\generated\audit-integrity.json
start "" "%CD%\reports\generated"
pause
