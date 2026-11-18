@echo off
setlocal
cd /d "%~dp0"
python scripts\verify_step63_discovery.py --output reports\step63_discovery_qualification.json
if errorlevel 1 exit /b %errorlevel%
python scripts\verify_store_release.py --output reports\step63_store_release_verification.json
if errorlevel 1 exit /b %errorlevel%
echo Step 63 Discovery qualification passed.
endlocal
