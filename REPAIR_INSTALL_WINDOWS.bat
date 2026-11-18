@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
set "PYTHON_EXE="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo ERROR: CPython 3.11.x x64 nahi mila. INSTALL_WINDOWS.bat run karein.
  popd
  pause
  exit /b 1
)
"%PYTHON_EXE%" "scripts\install_windows_step206.py" --source-root "." --force-repair
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
