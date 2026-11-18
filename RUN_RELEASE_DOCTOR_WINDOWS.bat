@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call "%CD%\RUN_STEP174_RELEASE_DOCTOR_WINDOWS.bat"
exit /b %ERRORLEVEL%
