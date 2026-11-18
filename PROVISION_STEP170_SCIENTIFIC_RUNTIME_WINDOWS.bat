@echo off
setlocal
cd /d "%~dp0"
echo.
echo BioIntel AI Step 170 - Specialist Scientific Runtime
echo -----------------------------------------------------
echo This provisions open-source specialist tools inside WSL2 using micromamba.
echo Provider/manual tools and licence-controlled downloads are NOT silently accepted.
echo.
if /I "%~1"=="--execute" goto execute
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\step170_provision_wsl.ps1"
echo.
echo Dry-run complete. To install, run:
echo   PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat --execute
exit /b %errorlevel%
:execute
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\step170_provision_wsl.ps1" -Execute
exit /b %errorlevel%
