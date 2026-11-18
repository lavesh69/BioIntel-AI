@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPATH=%CD%\src"
echo BioIntel AI Step 164 Specialist Runtime Manager
echo.
echo A safe dry-run will be generated first. No licence or provider terms are accepted automatically.
python scripts\step164_runtime_manager.py --root "%CD%" --backend micromamba
if errorlevel 1 exit /b %errorlevel%
echo.
echo Review reports\step164_runtime_manager.json.
echo To execute automatic open-source package installation, run:
echo python scripts\step164_runtime_manager.py --root "%CD%" --backend micromamba --execute
endlocal
