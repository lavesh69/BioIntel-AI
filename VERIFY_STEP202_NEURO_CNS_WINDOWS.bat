@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI Step202 - Full Neuro Verification
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  popd
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\verify_step202_neuro.py"
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
