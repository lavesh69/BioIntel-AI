@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
%PY% scripts\step167_build_priority_assets.py --root "%CD%"
exit /b %errorlevel%
