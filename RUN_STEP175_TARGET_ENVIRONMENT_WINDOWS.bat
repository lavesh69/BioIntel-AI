@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "MODE=Plan"
if /I "%~1"=="--execute-open" set "MODE=ExecuteOpen"
if /I "%~1"=="--resume" set "MODE=Resume"
if /I "%~1"=="--verify" set "MODE=Verify"
echo ============================================================
echo BioIntel AI Step 175 - Target Environment Qualification
echo ============================================================
echo Mode: %MODE%
echo Restricted licences and provider credentials are never accepted or stored automatically.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\step175_target_environment.ps1" -Mode %MODE%
exit /b %errorlevel%
