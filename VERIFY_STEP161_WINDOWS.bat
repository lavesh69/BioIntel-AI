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
  echo [BioIntel AI] Python 3.11 was not found.
  echo Run INSTALL_WINDOWS.bat first.
  exit /b 1
)

%PYTHON_EXE% "%CD%\scripts\step161_validate_upgrade.py" --root "%CD%" --quick
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [BioIntel AI] Step 161 verification failed. Review reports\step161_validation.json
  exit /b %RC%
)
echo [BioIntel AI] Step 161 verification passed.
exit /b 0
