@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
call "REPAIR_WINDOWS.bat" %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
