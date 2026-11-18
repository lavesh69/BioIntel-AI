@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHON_EXE="
for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE for /f "usebackq delims=" %%P in (`where python.exe 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo ERROR: Python 3.11 x64 was not found.
  pause
  exit /b 1
)
"%PYTHON_EXE%" "%PROJECT_ROOT%\scripts\step157_validate_installation.py" --root "%PROJECT_ROOT%" --allow-uninstalled
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Step 157 validation failed.
  pause
  exit /b %RC%
)
echo Step 157 validation passed.
pause
exit /b 0
