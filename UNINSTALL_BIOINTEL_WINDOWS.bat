@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI 15.6.0 Step220 - Safe Uninstall
if /I not "%~1"=="/managed" if exist "%LOCALAPPDATA%\BioIntelAI\App\UNINSTALL_BIOINTEL_ACTIVE.bat" (
  popd
  call "%LOCALAPPDATA%\BioIntelAI\App\UNINSTALL_BIOINTEL_ACTIVE.bat"
  exit /b
)
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY="
if not defined PY for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PY set "PY=%%P"
if not defined PY (
  echo ERROR: Python runtime was not found; uninstall could not verify the installed release.
  popd
  pause
  exit /b 1
)
echo This removes BioIntel application launchers and schedules the managed app for removal.
echo UserData, projects, reports, settings, databases and backups will be preserved.
set /p "CONFIRM=Type UNINSTALL to continue: "
if /I not "%CONFIRM%"=="UNINSTALL" (
  echo Uninstall cancelled. No files changed.
  popd
  exit /b 2
)
"%PY%" "scripts\uninstall_windows_step206.py" --root "." --confirmed
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
