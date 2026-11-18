@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe scripts\engineering_quality_gate.py --json-output reports\engineering_quality.json
if errorlevel 1 pause
