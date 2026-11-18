@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHON_EXE="
if exist "%CD%\.venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo [ERROR] Python was not found. Run INSTALL_WINDOWS.bat first.
  exit /b 1
)
"%PYTHON_EXE%" "%CD%\scripts\step159_validate_installation.py" --root "%CD%"
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" (
  echo.
  echo STEP 159 VALIDATION PASSED
) else (
  echo.
  echo STEP 159 VALIDATION FAILED. Review reports\step159_installation_validation.json
)
exit /b %RESULT%
