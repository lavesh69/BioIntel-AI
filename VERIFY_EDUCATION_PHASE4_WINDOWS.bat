@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "runtime\python\python.exe" set "PYTHON_EXE=runtime\python\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"
"%PYTHON_EXE%" scripts\verify_education_integrity_v2.py
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" scripts\verify_education_phase3.py
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" scripts\verify_education_phase4.py
if errorlevel 1 exit /b 1
echo.
echo BioIntel Education Phase 4 verification passed.
exit /b 0
