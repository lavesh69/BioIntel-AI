@echo off
setlocal EnableExtensions DisableDelayedExpansion
title BioIntel AI 15.6.0 Education Phase 14
set "PREFIX=BioIntel-AI-15.6.0-EDUCATION-PHASE14"
set "ARCHIVE_ROOT=BioIntel-Step220"
set "BASE=%LOCALAPPDATA%\BioIntelAI\InstallSource"
set "STAGE=%BASE%\Education-Phase14-%RANDOM%-%RANDOM%"
set "TAR=%SystemRoot%\System32\tar.exe"
set "EXTRACT_ONLY=0"
if /I "%~1"=="/extract-only" set "EXTRACT_ONLY=1"
echo ============================================================
echo BioIntel AI Education Phase 14 Academic Quality and Intelligence
echo Verified four-part Windows extraction and installation
echo ============================================================
for %%P in (1 2 3 4) do if not exist "%~dp0%PREFIX%-Part%%P.zip" (
  echo ERROR: Phase 14 ZIP Part %%P is missing beside this BAT file.
  pause
  exit /b 220
)
if not exist "%TAR%" (
  echo ERROR: Windows tar.exe is unavailable.
  pause
  exit /b 1
)
if not exist "%BASE%" mkdir "%BASE%" >nul 2>&1
mkdir "%STAGE%" >nul 2>&1
if not exist "%STAGE%" (
  echo ERROR: Short extraction folder could not be created: %STAGE%
  pause
  exit /b 1
)
for %%P in (1 2 3 4) do (
  echo [%%P/4] Extracting Part %%P...
  "%TAR%" -xf "%~dp0%PREFIX%-Part%%P.zip" -C "%STAGE%"
  if errorlevel 1 (
    echo ERROR: Part %%P extraction failed.
    pause
    exit /b 220
  )
)
set "SOURCE=%STAGE%\%ARCHIVE_ROOT%"
if not exist "%SOURCE%\INSTALL_WINDOWS.bat" (
  echo ERROR: BioIntel Phase 14 source is incomplete.
  pause
  exit /b 220
)
for %%P in (1 2 3 4) do if not exist "%SOURCE%\.release_parts\education_phase14_part%%P.ok" (
  echo ERROR: Education Phase 14 marker %%P is missing.
  pause
  exit /b 220
)
if "%EXTRACT_ONLY%"=="1" (
  echo Extraction completed: %SOURCE%
  pause
  exit /b 0
)
echo Extraction passed. Starting deep-verified installation...
call "%SOURCE%\INSTALL_WINDOWS.bat" /no-pause
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Installation failed with exit code %RC%.
  echo Review: %LOCALAPPDATA%\BioIntelAI\UserData\reports\step220-install.json
  pause
  exit /b %RC%
)
echo Installation completed. Starting BioIntel...
call "%LOCALAPPDATA%\BioIntelAI\App\RUN_BIOINTEL_ACTIVE.bat"
exit /b %ERRORLEVEL%
