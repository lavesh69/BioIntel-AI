@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
set "PYTHONPATH=%CD%\src"
"%PY%" scripts\step177_build_target_assets.py --root "%CD%"
if errorlevel 1 exit /b 1
echo Step 177 assets built.
