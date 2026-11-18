@echo off
setlocal
cd /d "%~dp0"
for %%D in (references fixtures governance evidence) do if not exist "UserData\step179\%%D" mkdir "UserData\step179\%%D"
call BUILD_STEP179_TARGET_MODULE_ASSETS_WINDOWS.bat
if errorlevel 1 exit /b 1
echo Step 179 intake folders and templates are ready.
echo Real evidence remains operator supplied and fail-closed.
endlocal
