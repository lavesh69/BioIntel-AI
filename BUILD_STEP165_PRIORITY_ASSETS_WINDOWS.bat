@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPATH=%CD%\src"
python scripts\step165_build_priority_assets.py --root "%CD%"
exit /b %errorlevel%
