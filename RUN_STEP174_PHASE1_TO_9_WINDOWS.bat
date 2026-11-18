@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo ============================================================
echo BioIntel AI Step 174 - Phase 1 to 9 Qualification Execution
echo ============================================================
echo.
echo This command completes all software-controlled preparation and checks.
echo Genuine provider access, real cohorts, laboratory results, experts and site history remain external evidence.
echo.

call BUILD_STEP174_PHASE1_TO_9_ASSETS_WINDOWS.bat
if errorlevel 1 goto :failed

call PREPARE_STEP174_ALL_WORKSPACES_WINDOWS.bat
if errorlevel 1 goto :failed

call RUN_STEP174_LOCAL_ENVIRONMENT_QUALIFICATION_WINDOWS.bat
if errorlevel 1 echo WARNING: Target environment probe has blockers. Review reports\step174_environment_probe.json

if /I "%~1"=="--execute-open" goto :executeopen
goto :verify

:executeopen
echo.
echo Installing automatically distributable specialist engines...
call PROVISION_STEP170_SCIENTIFIC_RUNTIME_WINDOWS.bat --execute
if errorlevel 1 echo WARNING: One or more engine installations require manual/provider action.
echo.
echo Downloading supported small open reference packs...
call DOWNLOAD_STEP170_REFERENCE_DATABASES_WINDOWS.bat --execute-small-open
if errorlevel 1 echo WARNING: One or more references require manual/provider action.

:verify
call VERIFY_STEP170_WINDOWS.bat
if errorlevel 1 goto :failed
call VERIFY_STEP171_WINDOWS.bat
if errorlevel 1 goto :failed
call VERIFY_STEP172_WINDOWS.bat
if errorlevel 1 goto :failed
call VERIFY_STEP173_WINDOWS.bat
if errorlevel 1 goto :failed
call VERIFY_STEP174_WINDOWS.bat
if errorlevel 1 goto :failed
call RUN_STEP174_RELEASE_DOCTOR_WINDOWS.bat
if errorlevel 1 goto :failed

echo.
echo STEP 174 SOFTWARE-CONTROLLED PHASE 1 TO 9 EXECUTION COMPLETED.
echo Open the app page: Phase 1-9 Real-World Qualification Execution.
echo External evidence status remains fail-closed until genuine artifacts pass.
exit /b 0

:failed
echo.
echo STEP 174 STOPPED SAFELY. No failed evidence gate was overridden.
echo Review reports\step174_*.json and UserData\step174\execution_workspaces.
exit /b 1
