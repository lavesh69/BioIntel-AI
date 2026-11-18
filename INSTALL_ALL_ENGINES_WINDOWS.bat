@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0BIOINTEL_ENGINE_SETUP.bat" Complete
exit /b %ERRORLEVEL%
