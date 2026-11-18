@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE exit /b 1
"%PYTHON_EXE%" "scripts\step192_support_bundle.py" --root "." --output "reports\step192\BioIntel-Step192-Support-Bundle.zip"
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" echo Support bundle created in reports\step192\
popd
pause
exit /b %RC%
