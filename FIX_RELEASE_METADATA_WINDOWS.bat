@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  popd
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\repair_step194_release_metadata.py" --root "."
set "RC=%ERRORLEVEL%"
popd
if "%RC%"=="0" echo Release metadata repair verified successfully.
pause
exit /b %RC%
