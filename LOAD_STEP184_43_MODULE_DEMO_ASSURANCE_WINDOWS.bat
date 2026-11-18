@echo off
setlocal
cd /d "%~dp0"
call BUILD_STEP184_43_MODULE_DEMO_ASSURANCE_WINDOWS.bat
if errorlevel 1 exit /b 1
call VERIFY_STEP184_43_MODULE_DEMO_ASSURANCE_WINDOWS.bat
if errorlevel 1 exit /b 1
echo Step 184 assurance bundles are ready in UserData\step184\advanced_demo_assurance.
pause
endlocal
