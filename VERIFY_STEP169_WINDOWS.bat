@echo off
setlocal
cd /d "%~dp0"
set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" scripts\step169_build_final_assets.py --root .
if errorlevel 1 exit /b %errorlevel%
"%PYTHON_EXE%" scripts\step169_validate_final_consolidation.py --root .
exit /b %errorlevel%
