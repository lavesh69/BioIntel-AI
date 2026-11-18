@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verify_step117_theme_navigation.py
) else (
  py -3.11 scripts\verify_step117_theme_navigation.py
)
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" pause
exit /b %ERR%
