@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "from biointel.step101.background import BackgroundJobService; print(BackgroundJobService(r'.', python_executable=r'.venv\Scripts\python.exe').start())"
pause
