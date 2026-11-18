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

echo Starting repaired BioIntel AI Step 50...
echo If an older BioIntel terminal is running, close it before continuing.
start "" "http://127.0.0.1:8501"
call .venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
