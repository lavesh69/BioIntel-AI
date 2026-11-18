@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo ERROR: Python 3.11 was not found.
  popd
  pause
  exit /b 1
)
"%PYTHON_EXE%" "scripts\step192_validate_release.py" --root "." --allow-uninstalled --deep-hashes --output "reports\step192\manual_verification.json"
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
