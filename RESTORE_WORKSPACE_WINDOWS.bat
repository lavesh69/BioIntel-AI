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

set "BACKUP_FILE=%~1"
if "%BACKUP_FILE%"=="" (
  set /p BACKUP_FILE=Enter the full path to the workspace backup ZIP: 
)

if "%BACKUP_FILE%"=="" (
  echo No backup file was provided.
  pause
  exit /b 1
)

call .venv\Scripts\python.exe -m biointel workspace-restore --backup "%BACKUP_FILE%"
if errorlevel 1 (
  echo Restore failed.
  pause
  exit /b 1
)

echo.
echo Restore completed. Existing files with the same name were skipped.
pause
