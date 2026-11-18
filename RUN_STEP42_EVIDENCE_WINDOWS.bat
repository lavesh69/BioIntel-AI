@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
python scripts\run_step42_verifiable_evidence.py --load-requests 400 --tenant-iterations 1000
if errorlevel 1 exit /b %errorlevel%
python scripts\qualify_step42_maximum_evidence.py
if errorlevel 1 exit /b %errorlevel%
python -m pytest -q tests\operations\test_step42_maximum_verifiable_evidence.py
endlocal
