@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Virtual environment missing. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
echo Running safe database, cache and runtime-log optimization...
".venv\Scripts\python.exe" "scripts\step123_optimize_workspace.py" --root "."
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo Optimization detected a problem. Review reports\step123_runtime_optimization.json
  pause
  exit /b %RC%
)
echo Optimization completed successfully.
pause
exit /b 0
