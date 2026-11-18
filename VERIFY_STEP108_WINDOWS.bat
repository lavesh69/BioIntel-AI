@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step108_decision_visuals.py
) else (
  python scripts\verify_step108_decision_visuals.py
)
set RC=%ERRORLEVEL%
if not "%RC%"=="0" echo Step 108 verification reported one or more failures.
exit /b %RC%
