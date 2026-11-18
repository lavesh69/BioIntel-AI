@echo off
setlocal
cd /d "%~dp0"

set "BIOINTEL_INTERNET_ENABLED=1"
set "BIOINTEL_ALLOW_PUBLIC_HTTPS=1"
set "BIOINTEL_OFFICIAL_HOSTS_ONLY=0"
set "BIOINTEL_RESOLVE_DNS=1"
set "BIOINTEL_MAX_DOWNLOAD_MB=250"
set "BIOINTEL_NETWORK_TIMEOUT=30"
set "BIOINTEL_NETWORK_RETRIES=2"

if not exist .venv\Scripts\python.exe (
  echo First-time setup is required.
  call INSTALL_WINDOWS.bat
  if errorlevel 1 exit /b 1
)

echo Starting BioIntel AI with secure outbound internet access...
call RUN_BOTH_WINDOWS.bat
