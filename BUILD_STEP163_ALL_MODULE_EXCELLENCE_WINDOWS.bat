@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
set PYTHONPATH=%CD%\src
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\step163_build_module_excellence.py --root "%CD%"
) else (
  python scripts\step163_build_module_excellence.py --root "%CD%"
)
if errorlevel 1 exit /b 1
echo Step 163 all-module excellence assets built successfully.
endlocal
