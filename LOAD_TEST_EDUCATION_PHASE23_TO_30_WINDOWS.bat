@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel Education Phase 23-30 Local Load Probe
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
if not defined BIOINTEL_USER_DATA_DIR set "BIOINTEL_USER_DATA_DIR=%LOCALAPPDATA%\BioIntelAI\UserData"
set "PY=%CD%\.venv\Scripts\python.exe"
set "PYARGS="
if not exist "%PY%" (
  set "PY=py"
  set "PYARGS=-3.11"
)
set "PROFILE=%~1"
if "%PROFILE%"=="" set "PROFILE=500"
if not exist "%BIOINTEL_USER_DATA_DIR%\reports" mkdir "%BIOINTEL_USER_DATA_DIR%\reports" >nul 2>&1
set "PYTHONPATH=%CD%\src"
"%PY%" %PYARGS% "scripts\load_test_education_phase23_30.py" --root "%CD%" --profile "%PROFILE%" --output "%BIOINTEL_USER_DATA_DIR%\reports\phase23-30-load-probe-%PROFILE%.json"
set "RC=%ERRORLEVEL%"
echo This is a bounded local probe, not a production capacity certification.
popd
if /I not "%~2"=="/no-pause" pause
exit /b %RC%
