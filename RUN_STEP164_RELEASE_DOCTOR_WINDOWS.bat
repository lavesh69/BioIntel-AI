@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONPATH=%CD%\src"
python scripts\step164_release_doctor.py --root "%CD%"
exit /b %errorlevel%
