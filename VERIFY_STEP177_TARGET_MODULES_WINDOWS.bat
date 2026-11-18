@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
set "PYTHONPATH=%CD%\src"
"%PY%" scripts\step177_verify_target_modules.py --root "%CD%"
exit /b %ERRORLEVEL%
