@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
REM The qualified current-release runtime preflight is executed by RUN_BOTH_WINDOWS.bat.
call "%~dp0RUN_BOTH_WINDOWS.bat"
exit /b %ERRORLEVEL%
