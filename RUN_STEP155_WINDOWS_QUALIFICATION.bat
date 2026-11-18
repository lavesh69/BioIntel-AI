@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "PYTHON_EXE="
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo ERROR: Python runtime not found. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
set "PYTHONDONTWRITEBYTECODE=1"
"%PYTHON_EXE%" "%PROJECT_ROOT%\scripts\step155_validate_installation.py" --root "%PROJECT_ROOT%"
if errorlevel 1 exit /b 1
set "PYTHONPATH=%PROJECT_ROOT%\src"
"%PYTHON_EXE%" -m pytest -q "%PROJECT_ROOT%\tests\test_step155_confirmatory_depth.py" "%PROJECT_ROOT%\tests\test_step154_maximum_internal_readiness.py"
if errorlevel 1 exit /b 1
echo Step 155 Windows qualification checks passed.
pause
exit /b 0
