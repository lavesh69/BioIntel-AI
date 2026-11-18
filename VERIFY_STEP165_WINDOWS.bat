@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPATH=%CD%\src"
python scripts\step165_validate_priority.py --root "%CD%"
exit /b %errorlevel%
