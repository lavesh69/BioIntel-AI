@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title BioIntel AI Step 145 - Overall Stability Qualification
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\step145_qualification.py" --root "."
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo STEP 145 OVERALL STABILITY QUALIFICATION PASSED.) else (echo STEP 145 QUALIFICATION FAILED WITH CODE %RC%.)
pause
exit /b %RC%
