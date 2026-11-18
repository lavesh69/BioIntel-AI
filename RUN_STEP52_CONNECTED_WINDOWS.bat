@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set "BIOINTEL_INTERNET_ENABLED=1"
set "BIOINTEL_ALLOW_PUBLIC_HTTPS=1"
set "BIOINTEL_OFFICIAL_HOSTS_ONLY=1"
set "BIOINTEL_RESOLVE_DNS=1"
if not defined BIOINTEL_CONNECTED_TIMEOUT set "BIOINTEL_CONNECTED_TIMEOUT=30"
if not defined BIOINTEL_CONNECTED_CONNECT_TIMEOUT set "BIOINTEL_CONNECTED_CONNECT_TIMEOUT=8"
if not defined BIOINTEL_CONNECTED_RETRIES set "BIOINTEL_CONNECTED_RETRIES=3"
if not defined BIOINTEL_CONNECTED_CACHE_TTL set "BIOINTEL_CONNECTED_CACHE_TTL=86400"
if not defined OPENAI_STORE_RESPONSES set "OPENAI_STORE_RESPONSES=0"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment is missing.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)

echo Starting BioIntel AI Step 52 Connected Platform...
if defined OPENAI_API_KEY (
  echo OpenAI key: configured
) else (
  echo OpenAI key: missing - run CONFIGURE_STEP52_CONNECTIONS_WINDOWS.bat or use evidence-only mode
)
if defined NCBI_EMAIL (
  echo NCBI contact email: configured
) else (
  echo NCBI contact email: missing - recommended for NCBI E-utilities
)
start "" "http://127.0.0.1:8501"
call .venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
