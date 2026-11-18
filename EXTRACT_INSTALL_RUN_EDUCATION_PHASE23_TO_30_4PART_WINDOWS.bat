@echo off
setlocal EnableExtensions DisableDelayedExpansion
title BioIntel AI 15.6.0 Education Phase 23-30 - Extract Install Run
set "PREFIX=BioIntel-AI-15.6.0-EDUCATION-PHASE23-TO-30-ENTERPRISE-R1"
set "ARCHIVE_ROOT=BioIntel-Step220"
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "STAGE=%LOCALAPPDATA%\BioIntelAI\InstallSource\Education-Phase23-30-%RANDOM%-%RANDOM%"
set "TAR=%SystemRoot%\System32\tar.exe"
set "EXTRACT_ONLY=0"
set "INSTALL_ONLY=0"
if not "%~1"=="" for %%A in (%*) do (
  if /I "%%~A"=="/extract-only" set "EXTRACT_ONLY=1"
  if /I "%%~A"=="/install-only" set "INSTALL_ONLY=1"
)
for %%P in (1 2 3 4) do if not exist "%~dp0%PREFIX%-Part%%P.zip" (
  echo ERROR: %PREFIX%-Part%%P.zip is missing beside this script.
  exit /b 230
)
if not exist "%TAR%" (
  echo ERROR: Windows tar.exe is unavailable. Windows 10 or 11 is required.
  exit /b 1
)
mkdir "%STAGE%" >nul 2>&1
if not exist "%STAGE%" (
  echo ERROR: Short extraction path could not be created: %STAGE%
  exit /b 1
)
for %%P in (1 2 3 4) do (
  echo [%%P/4] Extracting verified Education Phase 23-30 package...
  "%TAR%" -xf "%~dp0%PREFIX%-Part%%P.zip" -C "%STAGE%"
  if errorlevel 1 exit /b 230
)
set "SOURCE=%STAGE%\%ARCHIVE_ROOT%"
if not exist "%SOURCE%\INSTALL_EDUCATION_PHASE23_TO_30_WINDOWS.bat" (
  echo ERROR: Extracted BioIntel-Step220 root is incomplete.
  exit /b 230
)
for %%P in (1 2 3 4) do if not exist "%SOURCE%\.release_parts\education_phase23_30_part%%P.ok" (
  echo ERROR: Education Phase 23-30 archive marker %%P is missing.
  exit /b 230
)
if "%EXTRACT_ONLY%"=="1" (
  echo Extraction verified: %SOURCE%
  exit /b 0
)
call "%SOURCE%\INSTALL_EDUCATION_PHASE23_TO_30_WINDOWS.bat"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" exit /b %RC%
if "%INSTALL_ONLY%"=="1" exit /b 0
call "%LOCALAPPDATA%\BioIntelAI\App\RUN_BIOINTEL_ACTIVE.bat"
exit /b %ERRORLEVEL%
