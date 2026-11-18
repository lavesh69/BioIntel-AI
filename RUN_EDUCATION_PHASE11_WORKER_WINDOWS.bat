@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON=%LocalAppData%\BioIntelAI\runtime\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set /p BIOINTEL_WORKER_ACTOR=Institution administrator user ID: 
if "%BIOINTEL_WORKER_ACTOR%"=="" (
  echo An institution administrator user ID is required.
  exit /b 2
)
"%PYTHON%" scripts\run_education_phase11_worker.py --actor "%BIOINTEL_WORKER_ACTOR%" --project-root "%CD%"
endlocal
