@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON_EXE=%%P"
)

if not exist "%PYTHON_EXE%" (
  echo ERROR: Python 3.11 not found. Run INSTALL_WINDOWS.bat first or install CPython 3.11 x64.
  popd
  pause
  exit /b 1
)

"%PYTHON_EXE%" "scripts\step216_release_readiness.py" --root "." %*
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo Step216 release readiness passed.
if not "%RC%"=="0" echo Step216 release readiness needs review. See reports\step216_release_readiness.json.
popd
pause
exit /b %RC%