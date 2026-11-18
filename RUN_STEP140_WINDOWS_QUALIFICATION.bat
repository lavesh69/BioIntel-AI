@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\step140_windows_qualification.py
) else (
  py -3.11 scripts\step140_windows_qualification.py
)
set EXIT_CODE=%ERRORLEVEL%
echo.
if %EXIT_CODE% EQU 0 (
  echo STEP 140 WINDOWS QUALIFICATION PASSED ON THIS MACHINE
) else (
  echo STEP 140 WINDOWS QUALIFICATION REPORTED BLOCKERS
)
echo Report: reports\step140_windows_qualification.json
pause
exit /b %EXIT_CODE%
