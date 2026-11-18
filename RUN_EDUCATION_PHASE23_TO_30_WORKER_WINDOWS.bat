@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel Education Phase 23-30 Worker
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
if not defined BIOINTEL_USER_DATA_DIR set "BIOINTEL_USER_DATA_DIR=%LOCALAPPDATA%\BioIntelAI\UserData"
set "PY=%CD%\.venv\Scripts\python.exe"
set "PYARGS="
if not exist "%PY%" (
  set "PY=py"
  set "PYARGS=-3.11"
)
set "PYTHONPATH=%CD%\src"
"%PY%" %PYARGS% -c "import sys;raise SystemExit(0 if sys.version_info[:2]==(3,11) and sys.maxsize>2**32 else 1)" >nul 2>&1
if errorlevel 1 (
  echo ERROR: 64-bit CPython 3.11 environment was not found.
  echo Run INSTALL_EDUCATION_PHASE23_TO_30_WINDOWS.bat first.
  popd
  exit /b 1
)
if "%~1"=="" goto AUTO_ACTOR
"%PY%" %PYARGS% "scripts\run_education_phase23_30_worker.py" --project-root "%CD%" --actor "%~1"
goto WORKER_DONE
:AUTO_ACTOR
"%PY%" %PYARGS% "scripts\run_education_phase23_30_worker.py" --project-root "%CD%"
:WORKER_DONE
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
