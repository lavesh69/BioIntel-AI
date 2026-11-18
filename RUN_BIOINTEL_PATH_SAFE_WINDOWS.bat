@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1 || exit /b 1
title BioIntel AI 15.6.0 Step220 - Path-Safe Startup
popd
call "%~dp0RUN_BOTH_WINDOWS.bat" %*
exit /b %ERRORLEVEL%
