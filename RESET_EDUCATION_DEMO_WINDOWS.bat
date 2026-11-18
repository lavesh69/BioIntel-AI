@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || (
  echo ERROR: BioIntel project folder open nahi ho paya.
  exit /b 1
)
set "BIOINTEL_DEMO_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%BIOINTEL_DEMO_PYTHON%" set "BIOINTEL_DEMO_PYTHON=python"
"%BIOINTEL_DEMO_PYTHON%" "%CD%\scripts\reset_biointel_education_demo.py" --project-root "%CD%"
set "BIOINTEL_DEMO_EXIT=%ERRORLEVEL%"
popd
endlocal & exit /b %BIOINTEL_DEMO_EXIT%
