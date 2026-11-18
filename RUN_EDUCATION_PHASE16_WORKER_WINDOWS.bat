@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ACTOR=%~1"
if not defined ACTOR set /p ACTOR=Institution administrator user ID for background jobs: 
if not defined ACTOR exit /b 2
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "runtime\python\python.exe" set "PY=runtime\python\python.exe"
if not defined PY set "PY=py -3.11"
set "PYTHONPATH=%CD%\src"
%PY% scripts\run_education_phase16_worker.py --actor "%ACTOR%" --project-root "%CD%"
exit /b %ERRORLEVEL%
