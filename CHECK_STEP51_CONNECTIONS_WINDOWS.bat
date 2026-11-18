@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing. Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -c "from biointel.connected import provider_rows, public_connection_status; import json; print(json.dumps({'configuration': public_connection_status(), 'providers': provider_rows()}, indent=2))"
pause
