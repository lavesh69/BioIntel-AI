@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step109_visual_interaction.py
) else (
  python scripts\verify_step109_visual_interaction.py
)
set RC=%ERRORLEVEL%
if not "%RC%"=="0" echo Step 109 verification reported one or more failures.
pause
exit /b %RC%
