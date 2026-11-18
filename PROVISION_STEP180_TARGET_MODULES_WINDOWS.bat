@echo off
setlocal
cd /d "%~dp0"
for %%D in (references models cohorts fixtures governance evidence) do if not exist "UserData\step180\%%D" mkdir "UserData\step180\%%D"
call BUILD_STEP180_TARGET_MODULE_ASSETS_WINDOWS.bat
if errorlevel 1 exit /b 1
echo Step 180 intake folders and manifest templates are ready.
echo Authentic external evidence remains operator supplied and fail-closed.
endlocal
