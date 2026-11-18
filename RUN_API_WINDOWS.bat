@echo off
setlocal
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "BIOINTEL_USER_DATA_DIR=%LOCALAPPDATA%\BioIntelAI\UserData"
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo Starting BioIntel AI API in NO-LOGIN LOCAL mode...
echo API documentation: http://127.0.0.1:8000/docs
call .venv\Scripts\python.exe -m uvicorn biointel.api.main:app --app-dir src --host 127.0.0.1 --port 8000
