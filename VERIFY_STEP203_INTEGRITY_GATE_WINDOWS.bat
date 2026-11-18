@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
set "PY="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PY set "PY=%%P"
if not defined PY (
  echo 64-bit CPython 3.11.9 was not found. Run INSTALL_WINDOWS.bat.
  popd
  pause
  exit /b 1
)
"%PY%" "scripts\step204_release_gate.py" --root "." --deep-hashes
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
