@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\step193_self_test.py" --root "." --output "reports\step193\manual_self_test.json"
set RC=%ERRORLEVEL%
popd
pause
exit /b %RC%
