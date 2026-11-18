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

set "REPORT_TITLE=BioIntel AI Research Workspace Report"
set /p REPORT_TITLE=Report title [%REPORT_TITLE%]: 
if "%REPORT_TITLE%"=="" set "REPORT_TITLE=BioIntel AI Research Workspace Report"

call .venv\Scripts\python.exe -m biointel workspace-report ^
  --title "%REPORT_TITLE%" ^
  --output reports\generated\BioIntel-AI-Workspace-Report.html

if errorlevel 1 (
  echo Report export failed.
  pause
  exit /b 1
)

echo.
echo Report created:
echo %CD%\reports\generated\BioIntel-AI-Workspace-Report.html
start "" "%CD%\reports\generated\BioIntel-AI-Workspace-Report.html"
pause
