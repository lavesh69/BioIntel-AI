@echo off
setlocal EnableExtensions DisableDelayedExpansion
title BioIntel AI 15.6.0 Education Phase 8 Visual UI - Extract Install and Run Both
set "PREFIX="
for %%N in (BioIntel-AI-15.6.0-EDUCATION-PHASE8 BioIntel-AI-15.6.0-EDUCATION-PHASE7 BioIntel-AI-15.6.0-EDUCATION-PHASE6 BioIntel-AI-15.6.0-EDUCATION-PHASE5 BioIntel-AI-15.6.0-EDUCATION-PHASE4 BioIntel-AI-15.6.0-EDUCATION-PHASE3 BioIntel-AI-15.6.0-EDUCATION-PHASE2 BioIntel-AI-15.6.0-EDUCATION-SCIENCE-ACADEMY BioIntel-AI-15.6.0-EDUCATION-UNIVERSE) do if not defined PREFIX if exist "%~dp0%%N-Part1.zip" set "PREFIX=%%N"
if not defined PREFIX (
  echo ERROR: No supported Education four-part release was found beside this BAT file.
  echo Supported names: EDUCATION-PHASE8, EDUCATION-PHASE7, EDUCATION-PHASE6, EDUCATION-PHASE5, EDUCATION-PHASE4, EDUCATION-PHASE3, EDUCATION-PHASE2, EDUCATION-SCIENCE-ACADEMY, EDUCATION-UNIVERSE.
  pause
  exit /b 220
)
set "ARCHIVE_ROOT=BioIntel-Step220"
set "BASE=%LOCALAPPDATA%\BioIntelAI\InstallSource"
set "STAGE=%BASE%\Education-Step220-%RANDOM%-%RANDOM%"
set "TAR=%SystemRoot%\System32\tar.exe"
set "EXTRACT_ONLY=0"
set "INSTALL_ONLY=0"
for %%A in (%*) do (
  if /I "%%~A"=="/extract-only" set "EXTRACT_ONLY=1"
  if /I "%%~A"=="/install-only" set "INSTALL_ONLY=1"
)

echo ============================================================
echo BioIntel AI 15.6.0 Education Phase 8 Visual UI - 4 Part Windows Installer
echo ============================================================
echo.
for %%P in (1 2 3 4) do if not exist "%~dp0%PREFIX%-Part%%P.zip" (
  echo ERROR: Education ZIP Part %%P is missing beside this BAT file.
  echo Keep this BAT and all four matching ZIP files in one folder.
  pause
  exit /b 220
)
if not exist "%TAR%" (
  echo ERROR: Windows tar.exe is unavailable. Use a current Windows 10 or 11 system.
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

echo Extracting all four verified parts to: %STAGE%
for %%P in (1 2 3 4) do (
  echo [%%P/4] Extracting Part %%P...
  "%TAR%" -xf "%~dp0%PREFIX%-Part%%P.zip" -C "%STAGE%"
  if errorlevel 1 (
    echo ERROR: Part %%P extraction failed. Re-copy or re-download that ZIP.
    pause
    exit /b 220
  )
)
set "SOURCE=%STAGE%\%ARCHIVE_ROOT%"
if not exist "%SOURCE%\INSTALL_WINDOWS.bat" (
  echo ERROR: Extracted BioIntel source is incomplete.
  pause
  exit /b 220
)
if /I "%PREFIX%"=="BioIntel-AI-15.6.0-EDUCATION-PHASE8" (
  for %%P in (1 2 3 4) do if not exist "%SOURCE%\.release_parts\education_phase8_part%%P.ok" (
    echo ERROR: Phase 8 archive marker %%P is missing after extraction.
    pause
    exit /b 220
  )
) else if /I "%PREFIX%"=="BioIntel-AI-15.6.0-EDUCATION-PHASE7" (
  for %%P in (1 2 3 4) do if not exist "%SOURCE%\.release_parts\education_phase7_part%%P.ok" (
    echo ERROR: Phase 7 archive marker %%P is missing after extraction.
    pause
    exit /b 220
  )
) else (
  for %%P in (1 2 3 4) do if not exist "%SOURCE%\.release_parts\shiro4_part%%P.ok" (
    echo ERROR: Four-part compatibility %%P marker is missing after extraction.
    pause
    exit /b 220
  )
)
for %%P in (1 2 3 4 5) do if not exist "%SOURCE%\.release_parts\step220_part%%P.ok" (
  echo ERROR: Step220 compatibility marker %%P is missing after extraction.
  pause
  exit /b 220
)
if "%EXTRACT_ONLY%"=="1" (
  echo Extraction and all release markers verified: %SOURCE%
  exit /b 0
)

echo.
echo Extraction verified. Installing with exact CPython 3.11.9 x64 contract...
call "%SOURCE%\INSTALL_WINDOWS.bat" /no-pause
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Installation failed with exit code %RC%.
  pause
  exit /b %RC%
)
if "%INSTALL_ONLY%"=="1" (
  echo Installation and native installer smoke tests passed.
  exit /b 0
)
echo.
echo Installation passed. Starting Streamlit UI and local FastAPI service...
call "%LOCALAPPDATA%\BioIntelAI\App\RUN_BIOINTEL_ACTIVE.bat"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo RUN BOTH exited with code %RC%.
  pause
  exit /b %RC%
)
exit /b 0

