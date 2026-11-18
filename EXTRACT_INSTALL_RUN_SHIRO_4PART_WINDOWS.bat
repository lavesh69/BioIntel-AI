@echo off
setlocal EnableExtensions DisableDelayedExpansion
title BioIntel AI 15.6.0 Shiro - Extract Install and Run Both
set "PREFIX=BioIntel-AI-15.6.0-SHIRO-FULL-WINDOWS-4PART"
set "ARCHIVE_ROOT=BioIntel-Step220"
set "BASE=%LOCALAPPDATA%\BioIntelAI\InstallSource"
set "STAGE=%BASE%\Shiro-Step220-%RANDOM%-%RANDOM%"
set "TAR=%SystemRoot%\System32\tar.exe"
set "EXTRACT_ONLY=0"
set "INSTALL_ONLY=0"
if not "%~1"=="" for %%A in (%*) do (
  if /I "%%~A"=="/extract-only" set "EXTRACT_ONLY=1"
  if /I "%%~A"=="/install-only" set "INSTALL_ONLY=1"
)

echo ============================================================
echo BioIntel AI 15.6.0 Shiro - 4 Part Windows Installer
echo ============================================================
echo.
for %%P in (1 2 3 4) do if not exist "%~dp0%PREFIX%-Part%%P.zip" (
  echo ERROR: Shiro ZIP Part %%P is missing beside this BAT file.
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
for %%P in (1 2 3 4) do if not exist "%SOURCE%\.release_parts\shiro4_part%%P.ok" (
  echo ERROR: Shiro physical Part %%P marker is missing after extraction.
  pause
  exit /b 220
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