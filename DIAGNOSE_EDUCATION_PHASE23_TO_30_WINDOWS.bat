@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel Education Phase 23-30 Diagnostics
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
if not defined BIOINTEL_USER_DATA_DIR set "BIOINTEL_USER_DATA_DIR=%LOCALAPPDATA%\BioIntelAI\UserData"
if not exist "%BIOINTEL_USER_DATA_DIR%\reports" mkdir "%BIOINTEL_USER_DATA_DIR%\reports" >nul 2>&1
set "PY=%CD%\.venv\Scripts\python.exe"
set "PYARGS="
if not exist "%PY%" (
  set "PY=py"
  set "PYARGS=-3.11"
)
set "PYTHONPATH=%CD%\src"
"%PY%" %PYARGS% "scripts\diagnose_education_phase23_30.py" --root "%CD%" --output "%BIOINTEL_USER_DATA_DIR%\reports\education-phase23-30-diagnostics.json"
set "RC=%ERRORLEVEL%"
echo Diagnostic report: %BIOINTEL_USER_DATA_DIR%\reports\education-phase23-30-diagnostics.json
popd
if /I not "%~1"=="/no-pause" pause
exit /b %RC%
