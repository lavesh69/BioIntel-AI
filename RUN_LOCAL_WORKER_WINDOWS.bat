@echo off
setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat 2>nul
python scripts\run_local_worker.py --worker-id local-windows-worker
