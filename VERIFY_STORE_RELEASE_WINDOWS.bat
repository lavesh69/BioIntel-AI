@echo off
setlocal
cd /d "%~dp0"
python scripts\verify_store_release.py --strict
pause
