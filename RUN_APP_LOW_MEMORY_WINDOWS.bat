@echo off
setlocal
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "BIOINTEL_USER_DATA_DIR=%LOCALAPPDATA%\BioIntelAI\UserData"
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set "BIOINTEL_LOW_MEMORY_MODE=1"
set "OMP_NUM_THREADS=2"
set "OPENBLAS_NUM_THREADS=2"
set "MKL_NUM_THREADS=2"
set "NUMEXPR_MAX_THREADS=2"
set "VECLIB_MAXIMUM_THREADS=2"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo Starting BioIntel AI in low-memory local mode...
echo Multi-gigabyte files should be registered through Local Data Manager instead of browser upload.
start "" "http://127.0.0.1:8501"
call .venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
