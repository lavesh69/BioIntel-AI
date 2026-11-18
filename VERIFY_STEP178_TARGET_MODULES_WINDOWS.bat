@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
"%PY%" scripts\step178_verify_target_modules.py --root .
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo Step 178 qualification failed. Review reports\step178_19_module_qualification.csv
if "%RC%"=="0" echo Step 178 internal qualification passed for 19 of 19 modules.
endlocal & exit /b %RC%
