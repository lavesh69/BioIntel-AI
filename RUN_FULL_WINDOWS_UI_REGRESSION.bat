@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title BioIntel AI Step 116 - Full Windows UI Regression
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\run_windows_ui_regression.py" --root "." --mode full --timeout 30
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo UI REGRESSION PASSED.
) else (
  echo UI REGRESSION REPORTED FAILURES. Review reports\ui_regression.
)
pause
exit /b %RC%
