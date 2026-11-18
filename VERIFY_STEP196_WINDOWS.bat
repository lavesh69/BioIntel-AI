@echo off
setlocal
pushd "%~dp0" >nul 2>&1 || exit /b 1
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "scripts\step196_validate_release.py" --root "." --allow-uninstalled --deep-hashes
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
