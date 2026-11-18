@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title BioIntel AI Step 147 - Research Lifecycle Operational Qualification
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\step147_qualification.py" --root "."
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo STEP 147 RESEARCH LIFECYCLE OPERATIONAL QUALIFICATION PASSED.) else (echo STEP 147 QUALIFICATION FAILED WITH CODE %RC%.)
pause
exit /b %RC%
