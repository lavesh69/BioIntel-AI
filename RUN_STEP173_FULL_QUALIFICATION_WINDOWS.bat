@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo BioIntel AI Step 173 - Full 80-Module Qualification
echo ============================================================
echo.

call BUILD_STEP173_FINAL_ALL_MODULE_ASSETS_WINDOWS.bat
if errorlevel 1 goto :failed

call VERIFY_STEP170_WINDOWS.bat
if errorlevel 1 goto :failed

call VERIFY_STEP171_WINDOWS.bat
if errorlevel 1 goto :failed

call VERIFY_STEP172_WINDOWS.bat
if errorlevel 1 goto :failed

call VERIFY_STEP173_WINDOWS.bat
if errorlevel 1 goto :failed

call RUN_STEP173_RELEASE_DOCTOR_WINDOWS.bat
if errorlevel 1 goto :failed

echo.
echo STEP 173 SOFTWARE QUALIFICATION COMPLETED.
echo Actual external release eligibility is evidence-bound and is shown in:
echo reports\step173_final_all_module_ratings.csv
echo.
exit /b 0

:failed
echo.
echo STEP 173 QUALIFICATION STOPPED SAFELY.
echo Review the command output and reports folder. No failed gate was overridden.
exit /b 1
