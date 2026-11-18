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

echo Available projects:
call .venv\Scripts\python.exe -m biointel project-list
if errorlevel 1 (
  echo Could not list projects.
  pause
  exit /b 1
)

echo.
set /p PROJECT_ID=Enter the project_id to export: 
if "%PROJECT_ID%"=="" (
  echo Project ID is required.
  pause
  exit /b 1
)

set "MODEL_FLAG="
set /p INCLUDE_MODEL=Include trusted model files? [y/N]: 
if /I "%INCLUDE_MODEL%"=="Y" set "MODEL_FLAG=--include-model-files"

if not exist reports\generated mkdir reports\generated
set "OUTPUT_FILE=reports\generated\%PROJECT_ID%-evidence-package.zip"

call .venv\Scripts\python.exe -m biointel evidence-package ^
  --project-id "%PROJECT_ID%" ^
  --output "%OUTPUT_FILE%" ^
  %MODEL_FLAG%

if errorlevel 1 (
  echo Evidence package export failed.
  pause
  exit /b 1
)

echo.
echo Evidence package created:
echo %CD%\%OUTPUT_FILE%
start "" "%CD%\reports\generated"
pause
