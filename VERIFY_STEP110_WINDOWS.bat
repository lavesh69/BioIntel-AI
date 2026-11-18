@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step110_advanced_viewers.py
) else (
  python scripts\verify_step110_advanced_viewers.py
)
set RC=%ERRORLEVEL%
if not "%RC%"=="0" echo Step 110 verification reported one or more failures.
pause
exit /b %RC%
