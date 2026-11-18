@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe scripts\qualify_step43_final.py
) else (
  python scripts\qualify_step43_final.py
)
if errorlevel 1 (
  echo.
  echo Final qualification FAILED. Review reports\step43_qualification.json
  exit /b 1
)
echo.
echo Final qualification PASSED. See reports\step43_qualification.json
