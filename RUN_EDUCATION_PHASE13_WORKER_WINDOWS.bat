@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" if exist "runtime\python\python.exe" set "PYTHON_EXE=runtime\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
set "BIOINTEL_WORKER_ACTOR=%~1"
if not defined BIOINTEL_WORKER_ACTOR set /p BIOINTEL_WORKER_ACTOR=Institution administrator user ID: 
if not defined BIOINTEL_WORKER_ACTOR (
  echo Administrator user ID is required.
  if "%~1"=="" pause
  exit /b 2
)
"%PYTHON_EXE%" scripts\run_education_phase13_worker.py --actor "%BIOINTEL_WORKER_ACTOR%" --project-root "%CD%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Phase 13 worker exited with code %RC%.
  if "%~1"=="" pause
)
exit /b %RC%
