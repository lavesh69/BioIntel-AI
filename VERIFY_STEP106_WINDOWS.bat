@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step106_ui_workbench.py
) else (
  python scripts\verify_step106_ui_workbench.py
)
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo Step 106 verification reported one or more failures.
pause
exit /b %RC%
