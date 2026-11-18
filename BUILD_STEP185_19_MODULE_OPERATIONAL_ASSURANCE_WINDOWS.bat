@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
%PY% scripts\step185_build_operational_assurance.py
if errorlevel 1 exit /b 1
echo Step 185 operational assurance built.
