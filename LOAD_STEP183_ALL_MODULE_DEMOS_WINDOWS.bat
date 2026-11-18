@echo off
setlocal
cd /d "%~dp0"
call BUILD_STEP183_ALL_MODULE_DEMOS_WINDOWS.bat
if errorlevel 1 exit /b 1
call VERIFY_STEP183_ALL_MODULE_DEMOS_WINDOWS.bat
if errorlevel 1 exit /b 1
echo.
echo All 80 synthetic demo bundles are ready.
echo Start the app with RUN_BOTH_WINDOWS.bat and open Step 183 All-Module Demo Center.
pause
endlocal
