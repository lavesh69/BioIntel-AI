@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" scripts\step176_build_target_assets.py
if errorlevel 1 (
  echo Step 176 asset build failed.
  pause
  exit /b 1
)
echo Step 176 target-module assets built successfully.
pause
endlocal
