@echo off
setlocal EnableExtensions DisableDelayedExpansion
title BioIntel AI Education Universe - Short Path Extract and Install
set "PREFIX=BioIntel-AI-15.6.0-EDUCATION-UNIVERSE"
set "ARCHIVE_ROOT=BioIntel-Step220"
set "BASE=%LOCALAPPDATA%\BioIntelAI\InstallSource"
set "STAGE=%BASE%\Step220-%RANDOM%-%RANDOM%"
set "TAR=%SystemRoot%\System32\tar.exe"

echo ============================================================
echo BioIntel AI Step220 - Safe Short-Path Extract and Install
echo ============================================================
echo.
for %%P in (1 2 3 4) do if not exist "%~dp0%PREFIX%-Part%%P.zip" (
  echo ERROR: Part %%P ZIP is missing beside this file.
  echo Keep this BAT and all four matching ZIPs in the same folder.
  pause
  exit /b 220
)
if not exist "%TAR%" (
  echo ERROR: Windows tar.exe is unavailable.
  echo Use a current Windows 10/11 system or extract all ZIPs into C:\BioIntel220.
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

echo Extracting all four parts to short path:
echo %STAGE%
for %%P in (1 2 3 4) do (
  echo [%%P/4] Extracting Part %%P...
  "%TAR%" -xf "%~dp0%PREFIX%-Part%%P.zip" -C "%STAGE%"
  if errorlevel 1 (
    echo ERROR: Part %%P extraction failed.
    echo ZIP may be incomplete or damaged. Download that part again.
    pause
    exit /b 220
  )
)
set "SOURCE=%STAGE%\%ARCHIVE_ROOT%"
if not exist "%SOURCE%\INSTALL_WINDOWS.bat" if exist "%STAGE%\INSTALL_WINDOWS.bat" set "SOURCE=%STAGE%"
if not exist "%SOURCE%\INSTALL_WINDOWS.bat" (
  echo ERROR: Extracted Step220 source root is incomplete.
  pause
  exit /b 220
)
for %%P in (1 2 3 4) do if not exist "%SOURCE%\.release_parts\step220_part%%P.ok" (
  echo ERROR: Extracted Step220 Part %%P marker is missing.
  pause
  exit /b 220
)

echo.
echo Extraction complete. Verified installation start ho rahi hai...
call "%SOURCE%\INSTALL_WINDOWS.bat" /no-pause
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Installation failed with exit code %RC%.
  pause
  exit /b %RC%
)
echo.
echo Step220 installation complete. RUN_BOTH_WINDOWS.bat ya Desktop shortcut use karein.
pause
exit /b 0
