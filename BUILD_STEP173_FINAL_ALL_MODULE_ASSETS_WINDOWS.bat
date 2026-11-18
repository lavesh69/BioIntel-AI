@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
%PY% scripts\step173_build_assets.py
if errorlevel 1 exit /b 1
%PY% scripts\step173_generate_ratings.py
exit /b %errorlevel%
