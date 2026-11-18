@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\step140_stress_matrix.py
) else (
  py -3.11 scripts\step140_stress_matrix.py
)
set EXIT_CODE=%ERRORLEVEL%
echo Report: reports\step140_stress_matrix.json
pause
exit /b %EXIT_CODE%
