@echo off
setlocal
cd /d "%~dp0"
call ".venv\Scripts\python.exe" scripts\step180_build_target_assets.py --root "%CD%"
if errorlevel 1 exit /b 1
echo Step 180 scientific qualification assets built.
endlocal
