@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
echo ============================================================
echo BioIntel AI Step 174 - Local Environment Probe
echo ============================================================
echo This report applies only to the machine executing this file.
%PY% scripts\step174_realworld_manager.py environment-probe
exit /b %errorlevel%
