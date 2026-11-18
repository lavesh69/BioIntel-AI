@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Run INSTALL_WINDOWS.bat first.
  popd
  pause
  exit /b 1
)
"%PY%" "scripts\verify_step204_windows_install_run.py" --root "." --installed-python "%PY%"
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
