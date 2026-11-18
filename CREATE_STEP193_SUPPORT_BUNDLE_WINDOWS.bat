@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo ERROR: Python 3.11 x64 not found.
  pause
  exit /b 1
)
"%PYTHON_EXE%" "scripts\step192_support_bundle.py" --root "." --output "reports\step193\BioIntel-Step193-Support-Bundle.zip"
set RC=%ERRORLEVEL%
popd
pause
exit /b %RC%
