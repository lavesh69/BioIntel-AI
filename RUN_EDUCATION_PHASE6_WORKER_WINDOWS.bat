@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set /p BIOINTEL_WORKER_ACTOR=Institution admin/worker actor ID: 
if "%BIOINTEL_WORKER_ACTOR%"=="" (
  echo Actor ID is required.
  exit /b 1
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run_education_phase6_worker.py --actor "%BIOINTEL_WORKER_ACTOR%" --worker-id "%COMPUTERNAME%-education" --queue default
) else (
  py -3 scripts\run_education_phase6_worker.py --actor "%BIOINTEL_WORKER_ACTOR%" --worker-id "%COMPUTERNAME%-education" --queue default
)
endlocal
