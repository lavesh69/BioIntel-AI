@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

if not exist backups mkdir backups

call .venv\Scripts\python.exe -m biointel workspace-backup --output backups\BioIntel-AI-Workspace-Backup.zip
if errorlevel 1 (
  echo Backup failed.
  pause
  exit /b 1
)

echo.
echo Backup created:
echo %CD%\backups\BioIntel-AI-Workspace-Backup.zip
pause
