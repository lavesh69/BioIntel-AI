@echo off
setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat 2>nul
python scripts\verify_step33.py
if errorlevel 1 exit /b 1
echo Step 33 verification passed.
