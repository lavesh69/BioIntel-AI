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

call .venv\Scripts\python.exe -m biointel executive-summary ^
  --output reports\generated\BioIntel-AI-Executive-Summary.json

if errorlevel 1 (
  echo Executive summary export failed.
  pause
  exit /b 1
)

echo.
echo Executive summary created:
echo %CD%\reports\generated\BioIntel-AI-Executive-Summary.json
start "" "%CD%\reports\generated"
pause
