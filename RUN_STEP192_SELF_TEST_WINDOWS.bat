@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  popd
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\step192_self_test.py" --root "." --output "reports\step192\manual_self_test.json"
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
