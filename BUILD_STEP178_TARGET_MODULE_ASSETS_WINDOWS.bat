@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
"%PY%" scripts\step178_build_target_assets.py --root .
if errorlevel 1 exit /b 1
echo Step 178 asset templates built successfully.
endlocal
