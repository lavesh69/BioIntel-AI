@echo off
setlocal
cd /d "%~dp0"
echo Validating store release source...
python scripts\verify_store_release.py --strict
if errorlevel 1 exit /b 1
echo.
echo Building Windows APPX and installer...
powershell -ExecutionPolicy Bypass -File scripts\store\build_windows_release.ps1
