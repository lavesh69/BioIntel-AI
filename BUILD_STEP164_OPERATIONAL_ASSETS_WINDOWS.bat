@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPATH=%CD%\src"
python scripts\step164_build_operational_assets.py --root "%CD%"
exit /b %errorlevel%
