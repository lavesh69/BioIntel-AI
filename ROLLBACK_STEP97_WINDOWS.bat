@echo off
setlocal EnableExtensions
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\rollback_step97.ps1" -InstallRoot "%LOCALAPPDATA%\B97" -UserDataRoot "%LOCALAPPDATA%\BioIntelAI\UserData"
if errorlevel 1 (echo Rollback failed.& pause& exit /b 1)
echo BioIntel AI Step 97 rollback completed.
pause
