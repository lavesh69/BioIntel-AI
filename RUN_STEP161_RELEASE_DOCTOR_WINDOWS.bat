@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPATH=%CD%\src"
set "PYTHON_EXE="
if exist "%CD%\.venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE where py >nul 2>nul && set "PYTHON_EXE=py -3.11"
if not defined PYTHON_EXE where python >nul 2>nul && set "PYTHON_EXE=python"
if not defined PYTHON_EXE (
  echo [ERROR] Python was not found. Run INSTALL_WINDOWS.bat first.
  exit /b 1
)
%PYTHON_EXE% "%CD%\scripts\step161_release_doctor.py" --root "%CD%"
exit /b %ERRORLEVEL%
