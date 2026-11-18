@echo off
setlocal
cd /d "%~dp0"
python scripts\qualify_step85_user_experience.py
if errorlevel 1 exit /b 1
echo Step 85 user-experience qualification passed.
