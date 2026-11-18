@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
if "%~1"=="" (
  echo Usage: %~nx0 "backup.zip" RESTORE-HASH8
  popd
  exit /b 2
)
if "%~2"=="" (
  echo ERROR: Explicit RESTORE-HASH8 confirmation is required.
  popd
  exit /b 2
)
set "PY=%CD%\.venv\Scripts\python.exe"
set "PYARGS="
if not exist "%PY%" (
  set "PY=py"
  set "PYARGS=-3.11"
)
set "PYTHONPATH=%CD%\src"
"%PY%" %PYARGS% "scripts\phase23_30_backup_restore.py" --root "%CD%" restore --archive "%~f1" --confirmation "%~2"
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
