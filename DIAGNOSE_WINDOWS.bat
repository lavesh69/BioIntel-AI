@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI 15.6.0 Step220 - Diagnostics
if /I not "%~1"=="/managed" if exist "%LOCALAPPDATA%\BioIntelAI\App\DIAGNOSE_BIOINTEL_ACTIVE.bat" (
  popd
  call "%LOCALAPPDATA%\BioIntelAI\App\DIAGNOSE_BIOINTEL_ACTIVE.bat"
  exit /b
)
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY="
if not defined PY for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\find_python311_windows.ps1" 2^>nul`) do if not defined PY set "PY=%%P"
if not defined PY (
  echo ERROR: CPython 3.11.9 x64 was not found.
  popd
  if /I not "%~1"=="/managed" pause
  exit /b 1
)
set "DEEP_ARG="
if /I "%~2"=="/deep" set "DEEP_ARG=--deep"
if /I "%~1"=="/deep" set "DEEP_ARG=--deep"
"%PY%" "scripts\diagnose_windows_step206.py" --root "." --support-bundle %DEEP_ARG%
set "RC=%ERRORLEVEL%"
popd
if /I not "%~1"=="/managed" pause
exit /b %RC%
