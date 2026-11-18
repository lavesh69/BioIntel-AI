@echo off
setlocal
cd /d "%~dp0"
call ".venv\Scripts\python.exe" scripts\step179_build_target_assets.py --root "%CD%"
if errorlevel 1 exit /b 1
echo Step 179 assets built.
endlocal
