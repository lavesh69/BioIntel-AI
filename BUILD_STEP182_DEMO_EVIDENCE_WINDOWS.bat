@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
%PY% scripts\step182_build_demo_evidence.py
if errorlevel 1 exit /b 1
echo.
echo Step 182 synthetic demo evidence generated under UserData\step182\demo_evidence
exit /b 0
