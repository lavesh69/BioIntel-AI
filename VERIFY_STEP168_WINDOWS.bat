@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
%PY% scripts\step168_validate_remaining_modules.py --root "%CD%"
exit /b %errorlevel%
