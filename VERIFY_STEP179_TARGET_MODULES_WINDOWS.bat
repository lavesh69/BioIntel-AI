@echo off
setlocal
cd /d "%~dp0"
call ".venv\Scripts\python.exe" scripts\step179_verify_target_modules.py --root "%CD%"
set RC=%ERRORLEVEL%
if not "%RC%"=="0" echo Step 179 verification failed.
if "%RC%"=="0" echo Step 179 verification passed.
endlocal & exit /b %RC%
