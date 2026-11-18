@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BioIntel Education Services Setup

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo.
  echo [ERROR] BioIntel core environment is not installed.
  echo Run INSTALL_WINDOWS.bat first, then run this setup again.
  echo.
  pause
  exit /b 1
)

set "PYTHONPATH=%CD%\src"
echo.
echo ============================================================
echo  BioIntel Education Services Setup
echo ============================================================
echo  Local lessons, notes, assessments, Q&A, coding lab,
echo  offline library, resumes and credentials need no service.
echo  This setup only configures optional institutional endpoints.
echo ============================================================
echo.
"%PYTHON_EXE%" "%CD%\scripts\setup_biointel_education_services.py"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [OK] BioIntel Education services configuration completed.
) else (
  echo [NOTICE] Configuration was saved, but one or more enabled endpoints are unavailable.
)
pause
exit /b %RC%
