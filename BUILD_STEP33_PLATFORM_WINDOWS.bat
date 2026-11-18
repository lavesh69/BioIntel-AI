@echo off
setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat 2>nul
python scripts\build_step33_platform.py
if errorlevel 1 exit /b 1
echo Step 33 platform foundation built successfully.
