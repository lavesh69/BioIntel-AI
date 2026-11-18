@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI 15.6.0 Step220 - Safe Mode
if /I not "%~1"=="/managed" if exist "%LOCALAPPDATA%\BioIntelAI\App\SAFE_MODE_BIOINTEL_ACTIVE.bat" (
  popd
  call "%LOCALAPPDATA%\BioIntelAI\App\SAFE_MODE_BIOINTEL_ACTIVE.bat"
  exit /b
)
set "BIOINTEL_SAFE_MODE=1"
set "BIOINTEL_OFFLINE=1"
set "BIOINTEL_INTERNET_ENABLED=0"
set "BIOINTEL_ALLOW_PUBLIC_HTTPS=0"
set "BIOINTEL_OFFICIAL_HOSTS_ONLY=1"
set "BIOINTEL_RESOLVE_DNS=0"
set "BIOINTEL_DISABLE_OPTIONAL_ENGINES=1"
set "BIOINTEL_LOW_MEMORY_MODE=1"
call "STOP_BIOINTEL_WINDOWS.bat" /managed >nul 2>&1
call "RUN_BOTH_WINDOWS.bat" /managed
set "RC=%ERRORLEVEL%"
popd
if /I not "%~1"=="/managed" if not "%RC%"=="0" pause
exit /b %RC%
