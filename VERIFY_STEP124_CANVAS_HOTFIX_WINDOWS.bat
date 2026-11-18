@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step124_canvas_hotfix.py
) else (
  py -3.11 scripts\verify_step124_canvas_hotfix.py
)
if errorlevel 1 (
  echo.
  echo CANVAS HOTFIX VERIFICATION FAILED
  pause
  exit /b 1
)
echo.
echo CANVAS HOTFIX VERIFICATION PASSED
pause
