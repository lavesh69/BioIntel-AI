@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step131_realtime_interaction.py
) else (
  python scripts\verify_step131_realtime_interaction.py
)
if errorlevel 1 (
  echo.
  echo STEP 131 VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo STEP 131 VERIFICATION PASSED
pause
endlocal
