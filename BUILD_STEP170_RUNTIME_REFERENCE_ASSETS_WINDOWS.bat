@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
python scripts\step170_build_assets.py --root "%CD%"
exit /b %errorlevel%
