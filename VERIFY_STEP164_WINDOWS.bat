@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPATH=%CD%\src"
python scripts\step164_validate_operational.py --root "%CD%"
exit /b %errorlevel%
