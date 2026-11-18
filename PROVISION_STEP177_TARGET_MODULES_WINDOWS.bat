@echo off
setlocal
cd /d "%~dp0"
call BUILD_STEP177_TARGET_MODULE_ASSETS_WINDOWS.bat
if errorlevel 1 exit /b 1
call VERIFY_STEP177_TARGET_MODULES_WINDOWS.bat
exit /b %ERRORLEVEL%
