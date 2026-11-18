@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set "BIOINTEL_INTERNET_ENABLED=1"
set "BIOINTEL_ALLOW_PUBLIC_HTTPS=1"
set "BIOINTEL_OFFICIAL_HOSTS_ONLY=1"
set "BIOINTEL_RESOLVE_DNS=1"
set "BIOINTEL_CONNECTED_TIMEOUT=30"
set "BIOINTEL_CONNECTED_RETRIES=2"
set "BIOINTEL_CONNECTED_CACHE_TTL=86400"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo Starting BioIntel AI Step 51 Connected Platform...
echo OpenAI is optional. You can enter a session-only key inside BioIntel Copilot.
echo For environment configuration, set OPENAI_API_KEY, OPENAI_MODEL, NCBI_API_KEY and NCBI_EMAIL before launching.
start "" "http://127.0.0.1:8501"
call .venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
