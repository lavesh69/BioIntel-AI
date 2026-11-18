@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "NO_PAUSE=0"
set "NO_BROWSER=0"
set "INSTALL_ONLY=0"
set "PREFLIGHT_ONLY=0"
if not "%~1"=="" for %%A in (%*) do (
  if /I "%%~A"=="/no-pause" set "NO_PAUSE=1"
  if /I "%%~A"=="/no-browser" set "NO_BROWSER=1"
  if /I "%%~A"=="/install-only" set "INSTALL_ONLY=1"
  if /I "%%~A"=="/preflight-only" set "PREFLIGHT_ONLY=1"
)
pushd "%~dp0" >nul 2>&1 || (
  echo ERROR: BioIntel package folder open nahi ho paya.
  exit /b 1
)
title BioIntel AI 15.6.0 Step220 V20.5 - Install and Run
echo ============================================================
echo BioIntel AI 15.6.0 - Windows Install and Run
echo Phase31-to-35 Windows Fixed - Step220 V20.5
echo ============================================================
echo.

if not exist "app.py" goto :INCOMPLETE
for %%P in (1 2 3 4) do if not exist ".release_parts\step220_part%%P.ok" goto :INCOMPLETE
for %%F in ("INSTALL_WINDOWS.bat" "RUN_BOTH_WINDOWS.bat" "STEP220_RELEASE.json" "release\SOURCE_MANIFEST_SHA256.json") do if not exist %%F goto :INCOMPLETE

if "%PREFLIGHT_ONLY%"=="1" goto :PREFLIGHT

echo [1/2] Verified Windows installation start ho rahi hai...
call "INSTALL_WINDOWS.bat" /no-pause
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo ERROR: Installation complete nahi hui. Exit code %RC%.
  popd
  call :PAUSE_IF_NEEDED
  exit /b %RC%
)

if "%INSTALL_ONLY%"=="1" (
  echo.
  echo Installation verified and complete.
  popd
  call :PAUSE_IF_NEEDED
  exit /b 0
)

echo.
echo [2/2] BioIntel AI start ho raha hai...
if "%NO_BROWSER%"=="1" (
  call "RUN_BOTH_WINDOWS.bat" /no-browser /no-pause
) else (
  call "RUN_BOTH_WINDOWS.bat" /no-pause
)
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
  echo.
  echo ERROR: BioIntel AI start nahi hua. Exit code %RC%.
  call :PAUSE_IF_NEEDED
)
exit /b %RC%

:PREFLIGHT
call "INSTALL_WINDOWS.bat" /short-source /preflight-only /no-pause
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

:INCOMPLETE
echo ERROR: Four-part package incomplete hai.
echo Matching Part1, Part2, Part3 aur Part4 ZIPs ek hi destination mein extract karein.
echo Phir BioIntel-Step220\START_HERE_WINDOWS.bat dobara run karein.
popd
call :PAUSE_IF_NEEDED
exit /b 220

:PAUSE_IF_NEEDED
if "%NO_PAUSE%"=="0" pause
exit /b 0
