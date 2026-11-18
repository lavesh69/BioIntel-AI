@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "BIOINTEL_INTERNET_ENABLED=1"
set "BIOINTEL_ALLOW_PUBLIC_HTTPS=1"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0INSTALL_WINDOWS.bat"
  if errorlevel 1 exit /b 1
)
call "%~dp0RUN_BOTH_WINDOWS.bat"
exit /b %ERRORLEVEL%
