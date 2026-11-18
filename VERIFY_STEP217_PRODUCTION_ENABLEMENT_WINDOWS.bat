@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  where py >nul 2>&1 || (
    echo ERROR: Python 3.11 runtime not found.
    exit /b 1
  )
  set "PYTHON=py -3.11"
)

set "PYTHONPATH=%CD%\src"
%PYTHON% scripts\step217_release_gate.py --output reports\step217_release_gate.json
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Step217 software control verification failed.
  exit /b %RC%
)
echo Step217 software controls passed. External scientific and production evidence remains separately gated.
exit /b 0
